"""
Shared game changelog — imported by the context processor so every
template can access ``changelog`` and ``latest_update``.
Add newest entries at the TOP of the list.
"""

CHANGELOG = [
    {
        'version': '0.3.2-beta',
        'title': 'v0.3.2 Beta Release',
        'date': '2026-03-17',
        'body': (
            'Welcome to NationsEngine beta.  The beta phase is intended '
            'to be a balancing period and will focus on resource balancing. '
            'The main features of the game have been completed.'
        ),
    },
    {
        'version': '0.3.1-alpha',
        'title': 'v0.3.1 Mobile-Readiness',
        'date': '2026-03-16',
        'body': (
            'Welcome to NG4. This version includes some final touch-ups '
            'to the mobile view in preparation for the beta release.  I '
            'expect this to be the final alpha release.'
        ),
    },
    {
        'version': '0.3.0-alpha',
        'title': 'v0.3.0 War!',
        'date': '2026-03-15',
        'body': (
            'Welcome to NG4. Project is approaching the end of '
            'of its alpha phase.  This version introduces 1v1 PvP conflict '
            'via the war feature.  See military guide for details.'
        ),
    },
    {
        'version': '0.2.3-alpha',
        'title': 'v0.2.3 Buildings',
        'date': '2026-03-13',
        'body': (
            'Welcome to NG4. Project is approaching the end of '
            'of its alpha phase.  This version introduces industrial '
            'and recruitment buildings.  Alliance and mail QoL improved.'
        ),
    },
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
