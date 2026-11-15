"""Echo the command line; for downloads, drop a zip where the real CLI would."""

import os
import sys
import zipfile

args = sys.argv[1:]
print("KAGGLE", " ".join(args))
if "download" in args:
    dest = args[args.index("-p") + 1]
    with zipfile.ZipFile(os.path.join(dest, "data.zip"), "w") as z:
        z.writestr("train.csv", "id,label\n1,0\n")
