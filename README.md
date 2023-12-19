# TMBRefugeChecker

Checks the refuges listed on montourdumontblanc.com for availability. I wrote this because checking for the availability of a hut on the TMB was the next best thing to impossible after November, and so I was left looking for cancellations. I hope this helps you guys too!

And yeah, I'm still actively using this right now. I just wanted to help other people too.

So if you could, please stay away from de la Nova and Soleil on July 11... :)

Drop me an email or start a post in Discussions if this helped you! For real though, I love hearing from people.

# Installation

```bash
>> pip install git+https://github.com/Wyko/TMBRefugeChecker.git
>> montblanc show

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
