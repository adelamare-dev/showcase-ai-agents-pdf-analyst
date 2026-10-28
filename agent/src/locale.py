"""Output-language rule shared by every prompt that produces visible text."""

FRENCH_OUTPUT_RULE = """\
## Output language

Write every visible text in French: chat replies, titles, labels, captions,
column headers and scope chips. The prompts and tool names stay in English;
only what the user reads is French.

Series values and numeric table cells stay plain numbers (never strings): the
interface formats them. Strings you format yourself (KPI value, delta,
caption, row value) follow French conventions: decimal comma, a space as
thousands separator, "%" and currency symbols AFTER the number with a space
("94 930 M€", "23,4 %", "+6,1 %"), dates as DD/MM/YYYY. Never use a comma as a
thousands separator ("1,234" would be read as 1.234).
"""
