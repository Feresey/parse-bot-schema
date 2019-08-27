import time

import requests
from bs4 import BeautifulSoup
import os
import json

os.makedirs("public", exist_ok=True)
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


def determine_argtype(argtype):
    if argtype.startswith("Array of"):
        argtype = "array({0})".format(determine_argtype(argtype.replace("Array of ", "", 1)))

    if argtype in TYPE_OVERRIDES:
        argtype = TYPE_OVERRIDES[argtype]
    return argtype


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
            else:
                argdata["required"] = not row[-1].text.startswith("Optional.")
            argtypes = row[1].text.split(" or ")
            for argtype in argtypes:
                argtype = argtype.strip()
                argtype = determine_argtype(argtype)
                argdata["types"].append(argtype)
            arguments[row[0].text] = argdata
        return arguments


def gen_build_info():
    build_info = {}
    if os.getenv("CI", False):
        print("Building on CI")
        build_info["branch"] = os.getenv("CI_COMMIT_REF_NAME")
        build_info["commit"] = "%s (%s), build #%s, reason: %s" % (
            os.getenv("CI_COMMIT_SHORT_SHA"), os.getenv("CI_COMMIT_MESSAGE").replace("\n", ''),
            os.getenv("CI_PIPELINE_IID"),
            os.getenv("CI_PIPELINE_SOURCE"))
        build_info["pipeline_url"] = os.getenv("CI_PIPELINE_URL")
    else:
        print("Building locally.")
        build_info["branch"] = None
        build_info["commit"] = None
        build_info["pipeline_url"] = None
    build_info["timestamp"] = int(time.time())
    return build_info


def parse_botapi():
    r = requests.get("https://core.telegram.org/bots/api")
    soup = BeautifulSoup(r.text, features="lxml")
    schema = {"types": {}, "methods": {}, "version": soup.find_all("strong")[2].text.lstrip("Bot API "),
              "build_info": gen_build_info()}
    print("Building schema.json for Bot API version", schema["version"])
    for section in soup.find_all("h4"):
        title = section.text
        if not " " in title:
            description_soup = section.find_next_sibling()
            category = description_soup.find_previous_sibling("h3").text
            if title[0].islower():
                method = {"arguments": determine_arguments(description_soup),
                          "returns": determine_return(description_soup),
                          "description": escape_description(description_soup.text),
                          "category":category}
                schema["methods"][title] = method
                print("Adding method", title, "of category", category)
            else:
                type_ = {"fields": determine_arguments(description_soup),
                         "description": escape_description(description_soup.text),
                         "category":category}
                schema["types"][title] = type_
                print("Adding type", title, "of category", category)
    print(len(schema["types"]), "types")
    print(len(schema["methods"]), "methods")
    print("Build info:", schema["build_info"])
    with open("public/schema.json", 'w') as f:
        json.dump(schema, f, indent=4)


if __name__ == '__main__':
    parse_botapi()
