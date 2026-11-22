"""Centralized CEFR-aware prompts - single source of truth for all AI calls."""

LEVEL_SYSTEM = {
    'A2': """A2 = Beginner. VERY simple, 2-4 words, daily survival: greetings, food, directions, feelings. NO idioms yet, just useful chunks.
Examples: "How are you?", "Nice to meet you", "I am hungry", "Take your time", "Good morning" """,
    'B1': """B1 = Intermediate. Common idioms & collocations, 3-5 words, everyday life: work, travel, relationships.
Examples: "Piece of cake (=easy)", "Break a leg (=good luck)", "On cloud nine (=very happy)", "Cost an arm and a leg" """,
    'B2': """B2 = Upper-intermediate. Idioms/phrasal verbs, 3-6 words, workplace/social nuance.
Examples: "Hit the nail on the head", "Beat around the bush", "Bite the bullet", "Get cold feet" """,
    'C1': """C1 = Advanced. Sophisticated idioms, 3-7 words, nuanced/cultural.
Examples: "Take the bull by the horns", "Through thick and thin", "Make a mountain out of a molehill" """,
    'C2': """C2 = Mastery. Highly idiomatic, cultural, 3-7 words, native-like.
Examples: "The ball is in your court", "Elephant in the room", "Kick the can down the road" """,
}

EXPRESSIONS_SYSTEM = """You are an expert CEFR curriculum designer for spoken language.
You ONLY create CONVERSATIONAL, LEVEL-APPROPRIATE, useful spoken expressions that learners can actually USE in daily talk.
You NEVER create boring factual/scientific sentences like "Fossilization requires special circumstances" - those are REJECTED.
A good expression is something you'd hear in a movie, cafe, or office - not in a textbook."""

MEANING_SYSTEM = """You are a precise CEFR-level language tutor.
You teach EXACTLY at the learner's level - A2 simple, C2 sophisticated.
You use ONLY common everyday words (top 2000), Modern Standard Arabic Fusha if Arabic (no Egyptian dialect, no rare/literary words).
You are concise: meaning 2-4 words, usage 1 sentence, example 1 sentence, translation 1 sentence.
You never copy the phrase as the example, never invent movie details, never be verbose."""

# Few-shot for expressions per level (used as reference, not copied)
FEWSHOT_EXPRESSIONS = {
    'A2': 'How are you? (greetings), I am tired (health), Good morning (greetings)',
    'B1': 'Piece of cake (work/easy), On cloud nine (feelings), Break a leg (support)',
    'B2': 'Bite the bullet (decisions), Get cold feet (feelings), Hit the nail on the head (communication)',
    'C1': 'Take the bull by the horns (decisions), Water under the bridge (relationships)',
    'C2': 'Elephant in the room (communication), The ball is in your court (decisions)',
}
