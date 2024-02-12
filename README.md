# Tour du Mont Blanc Refuge Checker

Checks the refuges listed on (montourdumontblanc.com)[montourdumontblanc.com] (and one or two others) for availability. I wrote this because checking for the availability of a hut on the TMB was the next best thing to impossible after November, and so I was left looking for cancellations. I hope this helps you guys too!

~~And yes, I'm still actively using this right now. So if you could, please stay away from **de la Nova** and **Les Chambres du Soleil** on July 11... :smile:~~
Edit: I got the reservation! Whoo!

Please star the repo and start a post in Discussions if this helped you!

# Prerequisites

- Python 3.11
- Git

# Installation

```bash
pip install git+https://github.com/Wyko/TMBRefugeChecker.git
```

# Usage
After installing it, just open a terminal (Command Prompt) and type in the appropriate commands. 
All commands start with `montblanc`, and you can run `montblanc --help` to see guidance on how to use
it.
```bash
>> montblanc list

Found 40 refuges:
32400:   Auberge Gîte Bon Abri
32406:   Auberge Mont-Blanc
32394:   Auberge des Glaciers
32365:   Auberge du Truc
...

>> montblanc check 2024.07.01 32400 Glaciers Abri

!!! Refuge Auberge Gîte Bon Abri has 13 places left on Monday, Jul 01, 2024 !!!
<Beeping Alert Sounds>

>> montblanc check 2024.07.11 nova solei

Auberge-Refuge de la Nova has 0 places left on Thursday, Jul 11, 2024
Les Chambres du Soleil has 0 places left on Thursday, Jul 11, 2024
Waiting to check availability: 04:57
```

# Planning
This app can also be used to check a full trip's worth of dates. Doing so is easy:
```bash
>> montblanc plan day 2024.07.03 "lac blanc"
Added Wednesday, Jul 03, 2024:
  - Refuge du Lac Blanc

>> montblanc plan day 2024.07.11 "de la Nova" Soleil
Added Thursday, Jul 11, 2024:
  - Auberge-Refuge de la Nova
  - Les Chambres du Soleil

>> montblanc plan show
Wednesday, Jul 03, 2024:
  - Refuge du Lac Blanc
Thursday, Jul 11, 2024:
  - Les Chambres du Soleil
  - Auberge-Refuge de la Nova

>> montblanc plan check
Refuge Refuge du Lac Blanc is not yet bookable.
Les Chambres du Soleil has 0 places left on Thursday, Jul 11, 2024
Auberge-Refuge de la Nova has 0 places left on Thursday, Jul 11, 2024
Waiting to check availability: 04:40
```


# General Note

This script has plenty of caching and rate-limiting built in so we don't flood the website and make them angry. Don't mess with the rate limits, or this will end up broken _very_ quickly.
