Process a whole folder (recursive), PDFs only:

cd F:\\Jester\\dm\_cleaner

run\_pipeline.bat --input-dir "D:\\dnd5E\\Adventures" --input-glob "\*\*\\\*.pdf" --output-dir "F:\\Jester\\cleaned"



Include TXT/MD too (change the glob):

run\_pipeline.bat --input-dir "D:\\dnd5E\\Adventures" --input-glob "\*\*\\\*.\*" --output-dir "F:\\Jester\\cleaned"


Pass explicit files (no directory scan):
run\_pipeline.bat "D:\\dnd5E\\Adventures\\One-Shot Heist.pdf" "D:\\dnd5E\\Notes\\mystery.md" --output-dir "F:\\Jester\\cleaned"


Enable lenient theme/tone detection (catches extras outside your list):
run\_pipeline.bat --lenient --input-dir "D:\\dnd5E\\Adventures" --output-dir "F:\\Jester\\cleaned"


Point to your custom keywords file (instead of the built-in keywords.json):
set DM\_LEXICON\_PATH=F:\\Jester\\keywords\_merged\_tones100.json

run\_pipeline.bat --input-dir "D:\\dnd5E\\Adventures" --output-dir "F:\\Jester\\cleaned" --lenient


Tune chunk sizes (e.g., shorter training chunks):
run\_pipeline.bat --input-dir "D:\\dnd5E\\Adventures" --output-dir "F:\\Jester\\cleaned" --min-words 80 --max-words 350


Run directly with Python (no BAT wrapper):

python pipeline.py --input-dir "D:\\dnd5E\\Adventures" --output-dir "F:\\Jester\\cleaned"


Windows (PowerShell):

$env:DM\_LEXICON\_PATH = "F:\\Jester\\keywords\_merged\_tones100.json"

.\\run\_pipeline.bat --lenient --input-dir "D:\\dnd5E\\Adventures" --output-dir "F:\\Jester\\cleaned"


macOS / Linux:

cd ~/dm\_cleaner

chmod +x run\_pipeline.sh



\# PDFs only

./run\_pipeline.sh --input-dir "./adventures" --input-glob "\*\*/\*.pdf" --output-dir "./cleaned"



\# Include text/markdown too

./run\_pipeline.sh --input-dir "./adventures" --input-glob "\*\*/\*.\*" --output-dir "./cleaned" --lenient



\# Custom lexicon path

export DM\_LEXICON\_PATH="$HOME/keywords\_merged\_tones100.json"

./run\_pipeline.sh --input-dir "./adventures" --output-dir "./cleaned"



