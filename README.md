# utprint.py

A CLI program to send documents to UT Austin library
[printers](https://www.lib.utexas.edu/services/copyprint/). This is a faster
and simpler alternative to the official web
[interface](https://print.lib.utexas.edu/myprintcenter/).

After you log in for the first time, a cookie will be saved that allows
automatic reauthentication for the next two weeks. Your EID and password are
never stored.

```
usage: utprint.py [-h] [--color {full,mono}] [--sides {1,2}] [--two-pps]
                  [--copies COPIES] [--range RANGE]
                  document

Upload a document to UT's Library Print System.

positional arguments:
  document             a file (PDF, image, MS Office...) to print

optional arguments:
  -h, --help           show this help message and exit
  --color {full,mono}  print with or without color
  --sides {1,2}        print single sided (simplex) or double sided (duplex)
  --two-pps            print two pages on each side of paper
  --copies COPIES      print multiple copies
  --range RANGE        print a specific set of pages (e.g. '1-5, 8, 11-13')
```

Install dependencies: `pip3 install appdirs requests`

In action:

```
$ ./utprint.py ~/Documents/utcs.pdf
Print settings:
  - Full color
  - Simplex
  - Copies: 1
  - Page range: all
Logging in with saved token ... done
Uploading utcs.pdf ... done
Processing ... done
Finances:
    Available balance: $1.16
    Cost to print:     $0.42

    Remaining balance: $0.74
```

### Configuration

 * Linux: `~/.config/utprint/config.ini`
 * Windows: `C:\Users\<username>\AppData\Local\YoRyan\utprint\config.ini`
 * OS X: `~/Library/Application Support/utprint/config.ini`

```
[PrintDefaults]
color = full|mono
sides = 1|2

[PersistentAuth]
cookie = ...
```

### Legal

License: [MIT](https://opensource.org/licenses/MIT).
