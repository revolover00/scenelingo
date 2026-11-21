"""Bot profile configuration; no webhook, subscription or delivery changes."""
COMMANDS = [
    ('start', 'Set up or restart your subscription', 'إعداد الاشتراك أو البدء من جديد'),
    ('help', 'Help and available commands', 'المساعدة وقائمة الأوامر'),
    ('learn', 'Choose your learning language', 'اختيار لغة التعلّم'),
    ('level', 'Choose your learning level', 'اختيار المستوى'),
    ('explain', 'Choose your explanation language', 'اختيار لغة الشرح'),
    ('interval', 'Choose how often messages arrive', 'اختيار مواعيد الرسائل'),
    ('saved', 'View saved expressions', 'عرض التعبيرات المحفوظة'),
    ('review', 'Practise a saved expression', 'مراجعة تعبير محفوظ'),
    ('today', 'View the latest expression', 'عرض آخر تعبير متاح'),
    ('language', 'Change the bot interface language', 'تغيير لغة قوائم البوت'),
    ('stop', 'Pause your subscription', 'إيقاف الاشتراك مؤقتًا'),
]
PROFILES = {
    '': (
        ('Learn languages, one scene at a time. 🎬\n\n'
        'Discover real expressions through short movie scenes, with explanations for your level. '
        'Choose your learning language, explanation language and message frequency. '
        'Save expressions and practise with /review.\n\nTap /start to get started.'),
        'SceneLingo 🎬 Real expressions. Movie scenes. Learn at your own pace.',
    ),
    'en': (
        ('Learn languages, one scene at a time. 🎬\n\n'
        'Discover real expressions through short movie scenes, with explanations for your level. '
        'Choose your learning language, explanation language and message frequency. '
        'Save expressions and practise with /review.\n\nTap /start to get started.'),
        'SceneLingo 🎬 Real expressions. Movie scenes. Learn at your own pace.',
    ),
    'ar': (
        ('🎬 المشهد يعدّي، والتعبير يفضل معاك.\n\n'
        'اتعلّم تعبيرات حقيقية من مشاهد أفلام قصيرة، بشرح يناسب مستواك. '
        'اختار لغة التعلّم ولغة الشرح ومواعيد الرسائل. '
        'احفظ التعبيرات وراجعها على مهلك من /review.\n\nابدأ من /start.'),
        'SceneLingo 🎬 لغة من قلب المشهد. تعبيرات حقيقية تتعلّمها وتراجعها على مهلك.',
    ),
}


def configure_profile(api):
    """Apply and read back supported metadata. Never upload an unapproved logo."""
    for language, (description, short) in PROFILES.items():
        api('setMyName', name='SceneLingo', language_code=language)
        api('setMyDescription', description=description, language_code=language)
        api('setMyShortDescription', short_description=short, language_code=language)
        commands = [{'command': cmd, 'description': ar if language == 'ar' else en}
                    for cmd, en, ar in COMMANDS]
        # Default and all-private-chat scopes; explicit en/ar avoid stale overrides.
        for scope in ({'type': 'default'}, {'type': 'all_private_chats'}):
            api('setMyCommands', commands=commands, language_code=language, scope=scope)
            if api('getMyCommands', language_code=language, scope=scope) != commands:
                raise RuntimeError('Bot commands verification failed')
        for method, field, expected in (
            ('getMyName', 'name', 'SceneLingo'),
            ('getMyDescription', 'description', description),
            ('getMyShortDescription', 'short_description', short),
        ):
            if api(method, language_code=language).get(field) != expected:
                raise RuntimeError('Bot profile verification failed')
    api('setChatMenuButton', menu_button={'type': 'commands'})
    if api('getChatMenuButton').get('type') != 'commands':
        raise RuntimeError('Bot menu verification failed')
