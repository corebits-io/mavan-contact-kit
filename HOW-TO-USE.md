# How to use the Mavan contact kit

This kit finds the right person at a company, finds their work email, and checks that the email will land. It writes a spreadsheet. It never sends anything and it never writes a message.

## What you need
- A Mac or Linux machine with Python 3. Type `python3 --version` in Terminal to check. Nothing else to install.
- Claude Code, installed and signed in. Get it at claude.com/claude-code.
- Three accounts, each with an API key. An API key is a long password that lets the kit talk to the service.
  - Prospeo (prospeo.io). Finds the people at a company and their verified email.
  - Better Contact (bettercontact.rocks). A second, independent email finder. Catches what Prospeo misses.
  - BounceBan (bounceban.com). Checks whether an email will land. It cannot find an email, only judge one.

## Set up once, about ten minutes
1. Unzip the kit anywhere on your computer. Keep the folder name as it is.
2. In the folder, duplicate the file called `.env.example` and name the copy `.env`. Files that start with a dot are hidden on a Mac. Press Command, Shift and the full stop key together in Finder to show them.
3. Open `.env` in a plain text editor. Paste each key after its equals sign. Save. Never paste a key anywhere else, and never into a chat.
4. Open Terminal. Type `cd` and a space, drag the kit folder onto the Terminal window, press Enter. Then type `claude` and press Enter. Claude Code opens inside the kit and reads its own instructions.

## The three steps

### Step 1. Say who you are looking for
`ICP.md` already describes Mavan's two groups: owners of US consumer and subscription companies, and sell side bankers in the lower middle market. Edit that file when the target changes. Claude Code reads it before every search.

### Step 2. Find the person and the email, one company at a time
Tell Claude Code the company website and the group. For example: "find the founder or CEO at perfectsnacks.com, group A". Under the hood it runs this:
```
python3 skills/find-people/find_people.py --domain perfectsnacks.com --titles founder,ceo,"chief executive" --enrich 2 --fallback --out research/perfectsnacks.com.csv
```
For a banker the titles are managing director, partner, principal, founder.

The title filter matches any part of a title, so the word president would also catch a vice president and the word owner would catch a product owner. Stick to founder, ceo and chief executive for group A, and read the title column before you trust a row.

What happens: Prospeo lists everyone it knows at that domain. The script keeps the people whose title matches. It asks Prospeo for a verified email for the first one. If Prospeo has nothing, it asks Better Contact. Whatever comes back goes to BounceBan for a verdict. One company takes about thirty seconds, up to two minutes when Better Contact is asked.

Run companies one after another, never several at once. The services rate limit and the keys are tied to your account.

### Step 3. Keep only what passed
Open the output file in `research`. Look at the column called `bounceban`.
- `deliverable`: the mailbox exists and accepts mail. This row goes on the list.
- `risky`: the domain accepts every address, so nothing is proven about this one. It does not go on the list. Sending to risky rows is how a bounce rate climbs past three percent and a domain lands in spam.
- `undeliverable`: the address is dead. Drop it, even if a finder called it verified.
- empty: no email was found. The honest answer is not found. Never fill it with a guess.

## What each column means
- `full_name`, `title`, `company`, `domain`: who and where.
- `linkedin_url`: their profile, as Prospeo holds it.
- `email`: the address found.
- `email_status`: which finder found it and what that finder said, for example `prospeo VERIFIED` or `bettercontact deliverable`.
- `bounceban`: the verdict from Step 3. This is the column that decides.
- `mobile`: empty unless you ask for it. A mobile costs ten credits.

## Adding ten more contacts later
1. Pick ten company websites that fit `ICP.md`. Clay, LinkedIn, a trade directory or a conference list all work. If Clay is connected to your Claude account, the `build-list` skill in this kit can search it for you.
2. Ask Claude Code to run Step 2 on each one, one after another.
3. Keep the deliverable rows. Add them to the master spreadsheet. One person per company.
4. If the rows are more than three days old when you are ready to send, ask Claude Code to run BounceBan on the batch again. Addresses go stale.

## Rules that keep the list clean
- Never guess an email from a pattern. One guessed address that bounces hurts the sending domain for every email after it.
- One contact per company. Small companies talk to each other.
- Risky never goes on a send list.
- Keep `.env` private. If a key leaks, make a new one at the provider and paste it in.
- This kit does not write outreach. Messages are written later, by a person, in their own voice.

## What it costs
- Prospeo: one credit per company searched, plus one per verified email found.
- Better Contact: about seven credits each time it is asked.
- BounceBan: one credit per email checked.
Ten contacts normally use under thirty Prospeo credits, under seventy Better Contact credits and about ten BounceBan credits. The numbers are inside the standard plans of all three services.
