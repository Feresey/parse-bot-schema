import requests
from bs4 import BeautifulSoup
import os
import json

os.makedirs("build", exist_ok=True)
TYPE_OVERRIDES = {
    "String": "str",
    "Integer": "int",
    "Boolean": "bool"
}

REPLACEMENTS = {
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2014": "-",
    "\u2013": "-",
    "More info on Sending Files »": ""
}


def escape_description(description):
    for repl in REPLACEMENTS.items():
        description = description.replace(*repl)
    return description


def determine_return(description_soup):
    return_info = description_soup.text
    if "array" in return_info.lower():
        is_array = True
    else:
        is_array = False
    return_type = None
    links = description_soup.find_all("a")
    links.reverse()
    for item in links:
        if item.text[0].isupper():
            for sentence in return_info.split("."):
                sentence = sentence.lower()
                if item.text.lower() in sentence and "return" in sentence:
                    return_type = item.text
    if return_type:
        if is_array:
            return "array({})".format(return_type)
        else:
            return return_type
    else:
        for item in description_soup.find_all("em"):
            if item.text[0].isupper():
                return_type = item.text
        return return_type


def determine_arguments(description_soup):
    if "requires no parameters" in description_soup.text.lower():
        return {}
    else:
        table = description_soup.find_next_sibling("table")
        arguments = {}
        for row in table.find_all("tr")[1:]:  # Skip first row (headers)
            row = row.find_all("td")
            description = row[-1].text
            argdata = {"types": [], "description": escape_description(description)}
            if len(row) == 4:
                argdata["required"] = True if row[2].text == "Yes" else False
            argtypes = row[1].text.split(" or ")
            for argtype in argtypes:
                argtype = argtype.strip()
                if argtype in TYPE_OVERRIDES:
                    argtype = TYPE_OVERRIDES[argtype]
                argdata["types"].append(argtype)
            arguments[row[0].text] = argdata
        return arguments


def parse_botapi():
    r = requests.get("https://core.telegram.org/bots/api")
    soup = BeautifulSoup(r.text, features="lxml")
    schema = {"types": {}, "methods": {}, "version": soup.find_all("strong")[2].text.lstrip("Bot API ")}
    for section in soup.find_all("h4"):
        title = section.text
        if not " " in title:
            description_soup = section.find_next_sibling()
            if title[0].islower():
                method = {"arguments": determine_arguments(description_soup),
                          "returns": determine_return(description_soup),
                          "description": escape_description(description_soup.text)}
                schema["methods"][title] = method
            else:
                type_ = {"fields": determine_arguments(description_soup),
                         "description": escape_description(description_soup.text)}
                schema["types"][title] = type_
    with open("build/schema.json", 'w') as f:
        json.dump(schema, f, indent=4)
    with open("build/index.html", 'w') as f:
        f.write("<h1>this file is just for gitlab to pick up and deploy pages normally</h1>")


if __name__ == '__main__':
    parse_botapi()
