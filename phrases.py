"""Curated expressions organised by CEFR level and topic.

CEFR labels are approximate; learner ability and context vary.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

LEVELS = ('A2', 'B1', 'B2', 'C1', 'C2')

@dataclass(frozen=True)
class Phrase:
    text: str
    topic: str

# Short, useful spoken expressions are preferred so they can be matched to
# dialogue clips. Selection is limited to captions actually found on Yarn.
BANK = {
    'A2': [
        Phrase('How are you?', 'greetings'), Phrase('Nice to meet you', 'greetings'), Phrase('See you later', 'greetings'), Phrase('I have no idea', 'communication'), Phrase('What do you mean?', 'communication'),
        Phrase('I am not sure', 'communication'), Phrase('Take your time', 'support'), Phrase('Are you okay?', 'support'), Phrase('Be careful', 'safety'), Phrase('I am hungry', 'food'),
        Phrase('Let me help you', 'help'), Phrase('Where are you going?', 'travel'), Phrase('What happened?', 'events'), Phrase('I am sorry', 'feelings'), Phrase('That is a good idea', 'ideas'),
        Phrase('I need a break', 'work'), Phrase('I am on my way', 'travel'), Phrase('Can you help me?', 'help'), Phrase('What time is it?', 'time'), Phrase('I feel better', 'health'),
        Phrase('Good morning', 'greetings'), Phrase('Good night', 'greetings'), Phrase('How old are you', 'personal'), Phrase('Where do you live', 'travel'), Phrase('I love you', 'feelings'),
        Phrase('I miss you', 'feelings'), Phrase('Call me later', 'communication'), Phrase('Wait a minute', 'time'), Phrase('No problem', 'support'), Phrase('Thank you so much', 'greetings'),
        Phrase('Excuse me', 'communication'), Phrase('I do not know', 'communication'), Phrase('Come with me', 'travel'), Phrase('Look at this', 'communication'), Phrase('Let us go', 'travel'),
        Phrase('I am tired', 'health'), Phrase('It is okay', 'support'), Phrase('Do not worry', 'support'), Phrase('Happy birthday', 'greetings'), Phrase('Well done', 'support'),
        Phrase('Be quiet', 'communication'), Phrase('Hurry up', 'time'), Phrase('I am ready', 'work'), Phrase('Open the door', 'daily'), Phrase('Close the window', 'daily'),
        Phrase('Turn off the light', 'daily'), Phrase('I forgot', 'memory'), Phrase('I remember', 'memory'), Phrase('See you tomorrow', 'greetings'), Phrase('Talk later', 'communication'),
        Phrase('Hold on', 'communication'), Phrase('Listen to me', 'communication'), Phrase('Watch out', 'safety'), Phrase('I agree', 'discussion'), Phrase('I disagree', 'discussion'),
        Phrase('No way', 'feelings'), Phrase('Come on', 'communication'), Phrase('Go ahead', 'support'), Phrase('After you', 'greetings'), Phrase('My bad', 'feelings'),
        Phrase('Never mind', 'communication'), Phrase('Take care', 'support'), Phrase('Get well soon', 'health'), Phrase('Good luck', 'support'), Phrase('Have fun', 'support'),
        Phrase('Stay safe', 'safety'), Phrase('Calm down', 'support'), Phrase('Cheer up', 'support'), Phrase('Keep going', 'motivation'), Phrase('Do your best', 'motivation'),
        Phrase('You can do it', 'motivation'), Phrase('Believe in yourself', 'motivation'), Phrase('Dream big', 'motivation'), Phrase('Stay strong', 'support'), Phrase('Do not quit', 'motivation'),
        Phrase('Just do it', 'motivation'), Phrase('Make it happen', 'work'), Phrase('Time to shine', 'work'), Phrase('Let us celebrate', 'events'), Phrase('Well said', 'communication'),
        Phrase('That is true', 'discussion'), Phrase('Absolutely', 'communication'), Phrase('Exactly', 'communication'), Phrase('Of course', 'support'), Phrase('No doubt', 'discussion'),
        Phrase('For sure', 'communication'), Phrase('You bet', 'communication'), Phrase('Why not', 'ideas'), Phrase('Sounds good', 'ideas'), Phrase('Fair enough', 'discussion'),
        Phrase('All good', 'support'), Phrase('All set', 'work'), Phrase('Ready to go', 'travel'), Phrase('Let us roll', 'work'), Phrase('On my way', 'travel'),
        Phrase('See you soon', 'greetings'), Phrase('Catch you later', 'greetings'), Phrase('Until next time', 'greetings'), Phrase('Have a great day', 'greetings'), Phrase('Enjoy your day', 'greetings'),
        Phrase('Long time no see', 'greetings'), Phrase('What is new', 'communication'), Phrase('How have you been', 'communication'), Phrase('What is up', 'communication'), Phrase('Not much', 'communication'),
        Phrase('Same here', 'communication'), Phrase('Me too', 'communication'),
    ],
    'B1': [
        Phrase('It is up to you', 'decisions'), Phrase('I changed my mind', 'decisions'), Phrase('I cannot wait', 'feelings'), Phrase('I am looking forward to it', 'plans'), Phrase('That makes sense', 'communication'),
        Phrase('I did not mean that', 'communication'), Phrase('I am running late', 'time'), Phrase('I will figure it out', 'problems'), Phrase('I am proud of you', 'relationships'), Phrase('You have a point', 'discussion'),
        Phrase('Keep an eye on him', 'safety'), Phrase('I need to think', 'decisions'), Phrase('Let us get started', 'work'), Phrase('Do not give up', 'motivation'), Phrase('That is not fair', 'feelings'),
        Phrase('We are in trouble', 'problems'), Phrase('I will be right back', 'travel'), Phrase('It is worth a try', 'ideas'), Phrase('I do not feel well', 'health'), Phrase('You made my day', 'relationships'),
        Phrase('Piece of cake', 'work'), Phrase('Break a leg', 'support'), Phrase('Hit the books', 'work'), Phrase('Under the weather', 'health'), Phrase('Spill the beans', 'communication'),
        Phrase('Cost an arm and a leg', 'money'), Phrase('Once in a blue moon', 'time'), Phrase('Better late than never', 'time'), Phrase('So far so good', 'progress'), Phrase('The best of both worlds', 'life'),
        Phrase('Speak of the devil', 'greetings'), Phrase('Let the cat out of the bag', 'communication'), Phrase('Barking up the wrong tree', 'problems'), Phrase('Back to the drawing board', 'work'), Phrase('In the meantime', 'time'),
        Phrase('On the same page', 'work'), Phrase('Call it a day', 'work'), Phrase('Cut corners', 'work'), Phrase('Get something off your chest', 'feelings'), Phrase('On cloud nine', 'feelings'),
        Phrase('Down to earth', 'personality'), Phrase('Go the extra mile', 'work'), Phrase('Keep your chin up', 'support'), Phrase('Pull yourself together', 'support'), Phrase('Give me a hand', 'help'),
        Phrase('Keep in touch', 'relationships'), Phrase('Make up your mind', 'decisions'), Phrase('Lost track of time', 'time'), Phrase('Out of the blue', 'events'), Phrase('Around the clock', 'time'),
        Phrase('A blessing in disguise', 'life'), Phrase('Better safe than sorry', 'safety'), Phrase('Actions speak louder than words', 'life'), Phrase('Easy does it', 'support'), Phrase('Time flies', 'time'),
        Phrase('Hard to tell', 'communication'), Phrase('Make a difference', 'life'), Phrase('Take it easy', 'support'), Phrase('Hang in there', 'support'), Phrase('Come to think of it', 'thought'),
        Phrase('That rings a bell', 'memory'), Phrase('It takes two to tango', 'relationships'), Phrase('Every now and then', 'time'), Phrase('Far from it', 'discussion'), Phrase('Sooner or later', 'time'),
        Phrase('Up to now', 'time'), Phrase('As a matter of fact', 'communication'), Phrase('For the time being', 'time'), Phrase('In other words', 'communication'), Phrase('On the other hand', 'discussion'),
        Phrase('By the way', 'communication'), Phrase('In a nutshell', 'communication'), Phrase('All in all', 'summary'), Phrase('At the end of the day', 'life'), Phrase('Food for thought', 'ideas'),
        Phrase('A quick fix', 'problems'), Phrase('Set in stone', 'decisions'), Phrase('Go hand in hand', 'relationships'), Phrase('Keep an eye out', 'safety'), Phrase('Light at the end of the tunnel', 'hope'),
        Phrase('Make ends meet', 'money'), Phrase('On thin ice', 'risk'), Phrase('Pushing the envelope', 'risk'), Phrase('Saved by the bell', 'events'), Phrase('Second to none', 'praise'),
        Phrase('Through thick and thin', 'relationships'), Phrase('Up in the air', 'uncertainty'), Phrase('Worth its weight in gold', 'value'), Phrase('Off the top of my head', 'communication'), Phrase('Play it by ear', 'plans'),
        Phrase('Hit the sack', 'daily'), Phrase('Under wraps', 'communication'), Phrase('All ears', 'communication'), Phrase('Cross my mind', 'thought'), Phrase('Over the moon', 'feelings'),
        Phrase('Hands are tied', 'problems'), Phrase('Easier said than done', 'problems'), Phrase('Miss the boat', 'opportunity'), Phrase('On the fence', 'decisions'), Phrase('A drop in the ocean', 'value'),
        Phrase('Burn the midnight oil', 'work'), Phrase('Kill two birds with one stone', 'work'), Phrase('Let sleeping dogs lie', 'problems'), Phrase('Jump on the bandwagon', 'decisions'),
    ],
    'B2': [
        Phrase('Let us get to the point', 'communication'), Phrase('I will keep that in mind', 'communication'), Phrase('It slipped my mind', 'memory'), Phrase('We are on the same page', 'work'), Phrase('That is out of the question', 'decisions'),
        Phrase('I am having second thoughts', 'decisions'), Phrase('You are missing the point', 'discussion'), Phrase('I owe you one', 'relationships'), Phrase('Do not take it personally', 'relationships'), Phrase('Let us call it a day', 'work'),
        Phrase('We need to clear the air', 'relationships'), Phrase('I will take care of it', 'responsibility'), Phrase('You are in good hands', 'support'), Phrase('We are running out of time', 'time'), Phrase('I cannot make up my mind', 'decisions'),
        Phrase('I have a lot on my mind', 'feelings'), Phrase('That is easier said than done', 'problems'), Phrase('It is not what it looks like', 'communication'), Phrase('We have a lot in common', 'relationships'), Phrase('There is more to it', 'ideas'),
        Phrase('Get cold feet', 'feelings'), Phrase('Bite the bullet', 'decisions'), Phrase('Cut to the chase', 'communication'), Phrase('Against the clock', 'time'), Phrase('Through the grapevine', 'communication'),
        Phrase('Beat around the bush', 'communication'), Phrase('Hit the nail on the head', 'communication'), Phrase('Let the dust settle', 'time'), Phrase('Back against the wall', 'problems'), Phrase('Burn bridges', 'relationships'),
        Phrase('Add insult to injury', 'problems'), Phrase('Jump to conclusions', 'judgment'), Phrase('Keep at bay', 'problems'), Phrase('Lose track', 'memory'), Phrase('Make it up to you', 'relationships'),
        Phrase('On the back burner', 'work'), Phrase('Pull strings', 'work'), Phrase('Second thoughts', 'decisions'), Phrase('Bend over backwards', 'support'), Phrase('Face the music', 'responsibility'),
        Phrase('Get your act together', 'work'), Phrase('Give the benefit of the doubt', 'trust'), Phrase('In hot water', 'problems'), Phrase('Keep under wraps', 'communication'), Phrase('Look down on', 'judgment'),
        Phrase('Make a splash', 'events'), Phrase('Put in perspective', 'thought'), Phrase('Take for granted', 'relationships'), Phrase('Up to par', 'work'), Phrase('Weigh your options', 'decisions'),
        Phrase('At stake', 'risk'), Phrase('Call the shots', 'work'), Phrase('Cut your losses', 'money'), Phrase('Get under your skin', 'feelings'), Phrase('In the long run', 'time'),
        Phrase('Keep an open mind', 'ideas'), Phrase('On the verge of', 'time'), Phrase('Play devil advocate', 'discussion'), Phrase('Raise the bar', 'work'), Phrase('Steal the show', 'events'),
        Phrase('Take by surprise', 'events'), Phrase('Turn a blind eye', 'judgment'), Phrase('Worth a shot', 'decisions'), Phrase('Break the ice', 'communication'), Phrase('Cost the earth', 'money'),
        Phrase('Get the ball rolling', 'work'), Phrase('In deep water', 'problems'), Phrase('Jump the gun', 'time'), Phrase('Keep a low profile', 'communication'), Phrase('Learn the ropes', 'work'),
        Phrase('Make headway', 'progress'), Phrase('On the ball', 'work'), Phrase('Put your foot down', 'decisions'), Phrase('Rise above it', 'feelings'), Phrase('Sit on the fence', 'decisions'),
        Phrase('Take the lead', 'work'), Phrase('Under your nose', 'perception'), Phrase('Wear many hats', 'work'), Phrase('Bring to light', 'communication'), Phrase('Cross that bridge', 'problems'),
        Phrase('Get a grip', 'feelings'), Phrase('In the dark', 'knowledge'), Phrase('Keep in mind', 'memory'), Phrase('Lo and behold', 'events'), Phrase('On edge', 'feelings'),
        Phrase('Push your luck', 'risk'), Phrase('See through it', 'perception'), Phrase('Take it to heart', 'feelings'), Phrase('Up for grabs', 'opportunity'), Phrase('Work around the clock', 'work'),
        Phrase('Change your tune', 'discussion'), Phrase('Come full circle', 'life'), Phrase('Get the picture', 'communication'), Phrase('Lose your touch', 'work'), Phrase('Out of the woods', 'problems'),
    ],
    'C1': [
        Phrase('Let us cut to the chase', 'communication'), Phrase('That is beside the point', 'discussion'), Phrase('It is a blessing in disguise', 'life'), Phrase('I beg to differ', 'discussion'), Phrase('You are jumping to conclusions', 'judgment'),
        Phrase('Let us agree to disagree', 'discussion'), Phrase('I am in two minds', 'decisions'), Phrase('We are in the same boat', 'support'), Phrase('Do not beat around the bush', 'communication'), Phrase('It is a long shot', 'risk'),
        Phrase('That is the last straw', 'feelings'), Phrase('You have crossed the line', 'relationships'), Phrase('I will take your word for it', 'trust'), Phrase('Let us not get carried away', 'judgment'), Phrase('There is no point in arguing', 'discussion'),
        Phrase('I am at a loss', 'feelings'), Phrase('It is a matter of time', 'time'), Phrase('We have our work cut out for us', 'work'), Phrase('I have my reservations', 'decisions'), Phrase('Take it with a grain of salt', 'judgment'),
        Phrase('Throw caution to the wind', 'risk'), Phrase('Achilles heel', 'weakness'), Phrase('Bite off more than you can chew', 'work'), Phrase('Cut from the same cloth', 'relationships'), Phrase('Draw a blank', 'memory'),
        Phrase('Elvis has left the building', 'events'), Phrase('Go back to square one', 'work'), Phrase('In stitches', 'feelings'), Phrase('Keep peace', 'relationships'), Phrase('Let grass grow under your feet', 'time'),
        Phrase('Make a mountain out of a molehill', 'problems'), Phrase('Off the beaten path', 'travel'), Phrase('Pull your weight', 'work'), Phrase('Sell down the river', 'trust'), Phrase('Take the bull by the horns', 'decisions'),
        Phrase('Up your alley', 'interests'), Phrase('Wild goose chase', 'work'), Phrase('Bring home the bacon', 'work'), Phrase('Caught in the crossfire', 'problems'), Phrase('Down to the wire', 'time'),
        Phrase('Fit as a fiddle', 'health'), Phrase('Go down in flames', 'failure'), Phrase('In tandem', 'work'), Phrase('Know the ropes', 'work'), Phrase('Let it be', 'feelings'),
        Phrase('Make a beeline', 'travel'), Phrase('Pull out all the stops', 'work'), Phrase('Shoot from the hip', 'communication'), Phrase('Take the heat', 'responsibility'), Phrase('Under fire', 'problems'),
        Phrase('Water under the bridge', 'relationships'), Phrase('Break new ground', 'work'), Phrase('Clean bill of health', 'health'), Phrase('Down the drain', 'failure'), Phrase('Flog a dead horse', 'work'),
        Phrase('Go the distance', 'motivation'), Phrase('In high gear', 'work'), Phrase('Keep at arm length', 'relationships'), Phrase('Let the chips fall where they may', 'decisions'), Phrase('Make a killing', 'money'),
        Phrase('On a roll', 'success'), Phrase('Put on the back burner extra', 'work'), Phrase('Show your true colors', 'personality'), Phrase('Take with a grain of salt extra', 'judgment'), Phrase('Under the thumb', 'relationships'),
        Phrase('Wipe the slate clean', 'life'), Phrase('Burn the candle at both ends', 'work'), Phrase('Come out of your shell', 'personality'), Phrase('Drop in the bucket', 'value'), Phrase('Get wind of', 'knowledge'),
        Phrase('In a pickle', 'problems'), Phrase('Keep you on your toes', 'work'), Phrase('Like a fish out of water', 'feelings'), Phrase('Miss the mark', 'failure'), Phrase('On the same wavelength', 'relationships'),
        Phrase('Six feet under', 'life'), Phrase('Throw in the towel', 'motivation'), Phrase('Weather the storm', 'problems'), Phrase('Break a sweat', 'work'), Phrase('Cry over spilt milk', 'regret'),
        Phrase('Down to business', 'work'), Phrase('Head over heels', 'feelings'), Phrase('In over your head', 'problems'),
    ],
    'C2': [
        Phrase('The ball is in your court', 'decisions'), Phrase('It is a double-edged sword', 'risk'), Phrase('That is a moot point', 'discussion'), Phrase('The jury is still out', 'judgment'), Phrase('You are barking up the wrong tree', 'problems'),
        Phrase('We are treading on thin ice', 'risk'), Phrase('It is a slippery slope', 'risk'), Phrase('That is a tall order', 'work'), Phrase('Let us play devil advocate', 'discussion'), Phrase('It is a foregone conclusion', 'decisions'),
        Phrase('That is a blessing in disguise', 'life'), Phrase('We are at a crossroads', 'decisions'), Phrase('You have opened a can of worms', 'problems'), Phrase('The writing is on the wall', 'judgment'), Phrase('I would not hold my breath', 'expectations'),
        Phrase('It is a double whammy', 'problems'), Phrase('That is a bit of a stretch', 'discussion'), Phrase('There is no silver bullet', 'solutions'), Phrase('That is a bitter pill to swallow', 'feelings'), Phrase('It is a necessary evil', 'life'),
        Phrase('Elephant in the room', 'communication'), Phrase('Throw under the bus', 'trust'), Phrase('Cutting edge', 'work'), Phrase('Between a rock and a hard place', 'decisions'), Phrase('Devil is in the details', 'work'),
        Phrase('Kick the can down the road', 'decisions'), Phrase('Let the genie out of the bottle', 'problems'), Phrase('No stone unturned', 'work'), Phrase('Par for the course', 'expectations'), Phrase('Rub salt in the wound', 'feelings'),
        Phrase('Steer clear', 'safety'), Phrase('Whole nine yards', 'work'), Phrase('Beggars cannot be choosers', 'life'), Phrase('Fool me once', 'trust'), Phrase('Method to the madness', 'ideas'),
        Phrase('Penny for your thoughts', 'communication'), Phrase('Rule of thumb', 'knowledge'), Phrase('Spitting image', 'appearance'), Phrase('To each their own', 'judgment'), Phrase('Waste not want not', 'life'),
        Phrase('Bird in the hand', 'value'), Phrase('Clean slate', 'life'), Phrase('Every cloud has a silver lining', 'hope'), Phrase('Go against the grain', 'personality'), Phrase('Hindsight is twenty twenty', 'knowledge'),
        Phrase('Know by heart', 'memory'), Phrase('Loose cannon', 'personality'), Phrase('Make hay while the sun shines', 'opportunity'), Phrase('On thin ice deeper', 'risk'), Phrase('Shed light on', 'knowledge'),
        Phrase('Take under your wing', 'support'), Phrase('White elephant', 'money'), Phrase('Break the mold', 'personality'), Phrase('Come hell or high water', 'determination'), Phrase('Downward spiral', 'problems'),
        Phrase('Firing on all cylinders', 'work'), Phrase('Go pear shaped', 'failure'), Phrase('In dire straits', 'problems'), Phrase('Nip in the bud', 'problems'), Phrase('Out of the frying pan', 'problems'),
        Phrase('Put your cards on the table', 'communication'), Phrase('Throw down the gauntlet', 'challenge'), Phrase('Under the radar', 'communication'), Phrase('Butter someone up', 'communication'), Phrase('Come rain or shine', 'determination'),
        Phrase('Fly on the wall', 'perception'), Phrase('In full swing', 'events'), Phrase('Keep your powder dry', 'preparation'), Phrase('On the brink', 'risk'), Phrase('Rack your brains', 'thought'),
    ],
}


def candidates(level: str, seen: set[str], recent_topics: list[str]) -> list[Phrase]:
    """Prefer unseen expressions and topics, then recycle after exhaustion."""
    bank = BANK[level]
    pool = [p for p in bank if p.text.casefold() not in seen] or list(bank)
    pool = list(pool)
    random.shuffle(pool)
    return sorted(pool, key=lambda p: p.topic in recent_topics[:3])