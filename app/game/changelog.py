"""
Shared game changelog — imported by the context processor so every
template can access ``changelog`` and ``latest_update``.
Add newest entries at the TOP of the list.
"""

CHANGELOG = [
    {
        'version': '0.2.2-alpha',
        'title': 'v0.2.2 Battle Logs',
        'date': '2026-03-12',
        'body': (
            'Welcome to NG4. This is an early alpha.  This version '
            'introduces restyled battle logs with type-distinct content.'
        ),
    },
    {
        'version': '0.2.1-alpha',
        'title': 'v0.2.1 Military Training',
        'date': '2026-03-10',
        'body': (
            'Welcome to NG4. This is an early alpha.  This version '
            'introduces unit xp, vacation mode, and QoL improvements.'
        ),
    },
    {
        'version': '0.2.0-alpha',
        'title': 'NG4 Alpha — Phase 4.5',
        'date': '2026-03-10',
        'body': (
            'Welcome to NG4. This is an early alpha.  Missions '
            'and misc bugfixes have been added.'
        ),
    },
    {
        'version': '0.1.2-alpha',
        'title': 'NG4 Alpha — Phase 4',
        'date': '2026-03-10',
        'body': (
            'Welcome to NG4. This is an early alpha.  New additions '
            'include alliances and population growth automation.'
        ),
    },
    {
        'version': '0.1.1-alpha',
        'title': 'NG4 Alpha — Phase 3',
        'date': '2026-03-09',
        'body': (
            'Welcome to NG4. This is an early alpha.  Basic economics '
            'and military are complete.  Starvation and unit attrition '
            'has been implemented (units now heal 10% max HP per tick once '
            'upkeep is restored)'
        ),
    },
    {
        'version': '0.1.0-alpha',
        'title': 'NG4 Alpha — Phase 1',
        'date': '2026-03-08',
        'body': (
            'Welcome to NG4. This is an early alpha. Resources are '
            'deliberately unbalanced to let users experiment with features '
            'in short time. Military engine and trade are feature-complete. '
        ),
    },
]
