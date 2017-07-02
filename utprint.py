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


from base64 import b64encode
from getpass import getpass
from json import dumps
from mimetypes import guess_type
from os.path import basename
from urllib.parse import quote
import argparse
import requests
import sys


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
            ("content", (basename(filepath), open(filepath, "rb"),
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
    # command-line arguments
    parser = argparse.ArgumentParser(description=
                                     "Upload documents to UT's Library Print System.")
    parser.add_argument("-m", "--mono", dest="mono", action="store_true",
                        help="print without color (save money)")
    parser.add_argument("-d", "--duplex", dest="duplex", action="store_true",
                        help="print double sided (duplex)")
    parser.add_argument("-p", "--pages", dest="pages", nargs=1,
                        choices=["1", "2"], default=["1"],
                        help="print two pages on each side of paper")
    parser.add_argument("-c", "--copies", dest="copies", nargs=1,
                        type=int, default=[1],
                        help="print multiple copies")
    parser.add_argument("-r", "--range", dest="range", nargs=1, default=[""],
                        help="print a specific set of pages (e.g. '1-5, 8, 11-13')")
    parser.add_argument("document", nargs="+",
                        help="a file (PDF, image, MS Office...) to print")
    args = parser.parse_args()

    # build print settings JSON
    options = {
        "FinishingOptions": {
            "Mono": args.mono,
            "Duplex": args.duplex,
            "PagesPerSide": args.pages[0],
            "Copies": str(args.copies[0]),
            "DefaultPageSize": "Letter", # what's this? not in the web UI
            "PageRange": args.range[0]
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

    return 0

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