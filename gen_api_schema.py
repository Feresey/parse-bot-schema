import html
import time
from copy import copy

import html2markdown
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
BOT_API_URL = "https://core.telegram.org/bots/api"
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
            description_soup = row[-1]
            argdata = {"types": [], "description": gen_description(description_soup)}
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


def get_html(soup):
    for link in soup.find_all("a"):
        if link["href"].startswith("#") and not link.text == "":
            if "-" in link["href"]:
                # Article
                link["href"] = "#/articles/%s" % link["href"].split("#")[1]
            elif link.text[0].islower():
                # Method
                link["href"] = "#/methods/%s" % link.text
            else:
                # Probably type
                link["href"] = "#/types/%s" % link.text
    return str(soup).replace("<td>", "").replace("</td>", "").replace("<body>", "").replace("</body>", "")


def gen_description(soup):
    description = {}
    description["plaintext"] = escape_description(soup.text)
    description["html"] = get_html(soup)
    description["markdown"] = html.unescape(html2markdown.convert(description["html"]))
    return description


def get_article(description_soup):
    articles_text = str(description_soup)
    for sibling in list(description_soup.next_siblings):
        if sibling.name in ["h3", "h4"]:
            break
        else:
            articles_text += str(sibling)
    articles_soup = BeautifulSoup(articles_text, "lxml")
    article = gen_description(articles_soup.find("body"))
    return article


def generate_bot_api_data(schema, dwn_url=BOT_API_URL, update_version=False, changelog=False):
    r = requests.get(dwn_url)
    soup = BeautifulSoup(r.text, features="lxml")
    if update_version:
        schema["version"] = soup.find_all("strong")[2].text.lstrip("Bot API ")
    for section in soup.find_all(["h3", "h4"]):
        title = section.text
        description_soup = section.find_next_sibling()
        if not description_soup:
            continue
        category = description_soup.find_previous_sibling("h3").text
        if changelog:
            article = get_article(description_soup)
            version = description_soup.find("strong")
            if version and version.text.startswith("Bot API "):
                article["version"] = version.text.lstrip("Bot API ")
            else:
                article["version"] = title
            schema["changelogs"][title] = article
            print("Adding changelog", title)
        elif " " in title:
            if "Recent changes" in category:
                print("Changelog article, skipping to be added later")
                continue
            article_id = section.find("a")["name"]
            article = get_article(description_soup)
            article["title"] = title
            article["category"] = category
            schema["articles"][article_id] = article
            print("Adding article", title, "of category", category)
        elif title[0].islower():
            method = {"arguments": determine_arguments(description_soup),
                      "returns": determine_return(description_soup),
                      "description": gen_description(description_soup),
                      "category": category}
            schema["methods"][title] = method
            print("Adding method", title, "of category", category)
        else:
            type_ = {"fields": determine_arguments(description_soup),
                     "description": gen_description(description_soup),
                     "category": category}
            schema["types"][title] = type_
            print("Adding type", title, "of category", category)


def generate_schema():
    schema = {"types": {}, "methods": {}, "articles": {}, "changelogs": {}, "version": "Not found yet",
              "build_info": gen_build_info()}
    generate_bot_api_data(schema, update_version=True)
    print("Built schema for Bot API version", schema["version"])
    print("Getting changelogs...")
    generate_bot_api_data(schema, "https://core.telegram.org/bots/api-changelog", changelog=True)
    print(len(schema["types"]), "types")
    print(len(schema["methods"]), "methods")
    print("Build info:", schema["build_info"])
    with open("public/all.json", 'w') as f:
        json.dump(schema, f, indent=4)
    for name, data in schema.items():
        if name == "version":
            extension = "txt"
            write_data = data
        else:
            extension = "json"
            write_data = json.dumps(data, indent=4)
        with open("public/{}.{}".format(name, extension), 'w') as f:
            f.write(write_data)


if __name__ == '__main__':
    generate_schema()
