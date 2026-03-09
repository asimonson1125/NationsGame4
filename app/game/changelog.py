"""
Shared game changelog — imported by the context processor so every
template can access ``changelog`` and ``latest_update``.
Add newest entries at the TOP of the list.
"""

CHANGELOG = [
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
