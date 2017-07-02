#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# utprint.py
""" A simple CLI client for UT's Library Print System. """

# Copyright (c) 2017 Ryan Young (https://youngryan.com)

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


from appdirs import user_config_dir
from base64 import b64encode
from collections import namedtuple
from getpass import getpass
from json import dumps
from mimetypes import guess_type
from urllib.parse import quote
import argparse
import configparser
import os
import requests
import sys


CONFIG_DIR = user_config_dir("utprint", "YoRyan")
CONFIG_FILENAME = "config.ini"

Config = namedtuple("Config", ["color", "sides", "pharos_user_token"])

class PrintCenter:
    """Library of functions that interact with the Pharos API."""

    PRINT_SERVER = "https://print.lib.utexas.edu/PharosAPI"

    class LogonException(Exception):
        """Pharos login error."""
        pass

    class UploadException(Exception):
        """Pharos document upload error."""
        pass

    def logon(credentials):
        """Initiate a session with Pharos.

        credentials -- (eid, password) tuple

        Return a Requests.Session to interact with the Pharos API.
        """
        credentials = (encode_uricomp(credentials[0]),
                       encode_uricomp(credentials[1]))
        headers = {}
        headers["X-Authorization"] = ("PHAROS-USER " +
                                      encode_utf8_to_b64(credentials[0] + ":" +
                                                         credentials[1]))
        session = requests.Session()
        resp = session.get(PrintCenter.PRINT_SERVER + "/logon", headers=headers)
        if resp.status_code == requests.codes.ok:
            return session
        else:
            session.close()
            raise PrintCenter.LogonException(PrintCenter._error_msg(resp))

    def upload_file(session, options, filepath):
        """Upload a file to Pharos.

        session -- Request.Session from logon()
        options -- dictionary of document printing settings
        filepath -- path to document

        Return the parsed JSON response from the server.
        """
        files = [
            ("MetaData", (None, dumps(options))),
            ("content", (os.path.basename(filepath), open(filepath, "rb"),
                         mimetype(filepath)))
        ]
        resp = session.post(PrintCenter._user_uri(session) + "/printjobs",
                            files=files)
        if resp.status_code == requests.codes.created:
            try:
                return resp.json()
            except ValueError:
                raise PrintCenter.UploadException("warning: bad server response")
        else:
            raise PrintCenter.UploadException(PrintCenter._error_msg(resp))

    def _user_uri(session):
        """Extract user's API endpoint from the cookie jar.

        session -- Requests.Session from logon()
        """
        return (PrintCenter.PRINT_SERVER +
                session.cookies["PharosAPI.X-PHAROS-USER-URI"])

    def _error_msg(response):
        """Format an error message derived from a bad Requests response.

        response -- Requests.Response from a Requests.Request (ugh)
        """
        # TODO: handle networking errors
        try:
            rj = response.json()
            return str(response.status_code) + " error: " + rj["UserMessage"]
        except ValueError:
            return ("unknown " + str(response.status_code) + " error: " +
                    response.body)

def main():
    # read config file
    config = read_config_file()

    # command-line arguments
    parser = argparse.ArgumentParser(description=
                                     "Upload documents to UT's Library Print System.")
    parser.add_argument("--color", dest="color", choices=["color", "mono"], default=config.color,
                        help="print with or without color")
    parser.add_argument("--sides", dest="sides", type=int, choices=[1, 2], default=config.sides,
                        help="print single sided (simplex) or double sided (duplex)")
    parser.add_argument("--two-pps", dest="two_pages", action="store_true",
                        help="print two pages on each side of paper")
    parser.add_argument("--copies", dest="copies", type=int, default=1,
                        help="print multiple copies")
    parser.add_argument("--range", dest="range", default="",
                        help="print a specific set of pages (e.g. '1-5, 8, 11-13')")
    parser.add_argument("document", nargs="+",
                        help="a file (PDF, image, MS Office...) to print")
    args = parser.parse_args()

    # build print settings JSON
    if args.two_pages:
        pps = "2"
    else:
        pps = "1"
    options = {
        "FinishingOptions": {
            "Mono": args.color == "mono",
            "Duplex": args.sides == 2,
            "PagesPerSide": pps,
            "Copies": str(args.copies),
            "DefaultPageSize": "Letter", # what's this? not in the web UI
            "PageRange": args.range
        },
        "PrinterName": None
    }

    # read EID credentials
    creds = get_credentials()
    print()

    # login and upload each document
    print("Logging in ...", end="")
    with PrintCenter.logon(creds) as session:
        print(" done")
        for d in args.document:
            print("Uploading " + d + " ...", end="")
            try:
                PrintCenter.upload_file(session, options, d)
                print(" done")
            except PrintCenter.UploadException as err:
                print(" " + str(err))

    # save config file
    new_config = Config(color=config.color, sides=config.sides, pharos_user_token=
                        session.cookies["PharosAPI.X-PHAROS-USER-TOKEN"])
    write_config_file(new_config)

    return 0

def read_config_file():
    """Read user preferences from the configuration file.

    Return a Config tuple."""
    color = "color"
    sides = 1
    token = None
    parser = configparser.ConfigParser()
    parser.read(os.path.join(CONFIG_DIR, CONFIG_FILENAME))
    sections = parser.sections()
    if "PrintDefaults" in sections:
        fcolor = parser["PrintDefaults"].get("Color", None)
        if fcolor == "color" or fcolor == "mono":
            color = fcolor
        fsides = parser["PrintDefaults"].get("Sides", None)
        if fsides == "1" or fsides == "2":
            sides = int(fsides)
    if "PersistentAuth" in sections:
        token = parser["PersistentAuth"].get("Cookie", None)
    return Config(color=color, sides=sides, pharos_user_token=token)

def write_config_file(config):
    """Save user preferences to the configuration file.

    config -- Config tuple of stuff to save
    """
    writer = configparser.ConfigParser()
    writer["PrintDefaults"] = {}
    writer["PrintDefaults"]["Color"] = config.color
    writer["PrintDefaults"]["Sides"] = str(config.sides)
    writer["PersistentAuth"] = {}
    writer["PersistentAuth"]["Cookie"] = config.pharos_user_token
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(os.path.join(CONFIG_DIR, CONFIG_FILENAME), "w") as f:
        writer.write(f)

def get_credentials():
    # TODO: persistent storage
    return (input("EID: "), getpass())

def encode_utf8_to_b64(s):
    """Emulates Pharos's DIY base-64 encoder."""
    return b64encode(bytes(s, "utf-8")).decode("ascii")

# https://stackoverflow.com/questions/946170/equivalent-javascript-functions-for-pythons-urllib-quote-and-urllib-unquote
def encode_uricomp(s):
    """Emulates JavaScript's encodeURIComponent()."""
    return quote(s, safe="~()*!.'")

def mimetype(filepath):
    """Guess the mimetype of a file."""
    t = guess_type(filepath)
    if t[0] is None:
        return "application/octet-stream"
    else:
        return t[0]

if __name__ == "__main__":
    sys.exit(main())
