python dnd_statblock_toolkit_v2.py ingest "D:\dnd5E\Lore\Playable_Characters" ^
  --pattern "*.pdf" --recursive ^
  --output "D:\out\statblocks.json" ^
  --log-file "D:\out\statlogs.log" --log-level DEBUG ^
  --debug-dump "D:\out\debug_text" ^
  --min-signals 0 --no-skip-on-zero

also 

python dnd_statblock_toolkit_v2.py gui