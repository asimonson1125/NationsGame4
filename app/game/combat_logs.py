import random

# Battle Log Templates
# Format: (attacker_type, defender_type, hit_type) -> list of templates
# Use "Any" as a wildcard for attacker_type or defender_type.
# hit_type must be one of: 'critical', 'hit', 'graze', 'miss'
#
# Available placeholders:
# {attacker} - Name of the attacking unit
# {target} - Name of the defending unit
# {damage} - Damage dealt
# {target_hp} - Remaining HP of the target
# {target_max_hp} - Max HP of the target

BATTLE_LOG_TEMPLATES = {
    # --- INFANTRY ATTACKING ---
    ('Infantry', 'Infantry', 'miss'): [
        "{attacker} had a seemingly good plan, but the execution was horrible. {target} got lucky.",
        "{attacker} opened fire, but {target} dove into a nearby trench just in time.",
        "{attacker} was suppressed by return fire and couldn't find a clear shot at {target}.",
        "{attacker}'s rifles jammed at the worst possible moment while targeting {target}."
    ],
    ('Infantry', 'Infantry', 'graze'): [
        "{attacker} clipped {target} with a stray bullet, dealing {damage} damage.",
        "{target} was nearly hit by {attacker}'s volley, taking {damage} light damage.",
        "{attacker} forced {target} to keep their head down, scoring a lucky graze for {damage} damage."
    ],
    ('Infantry', 'Infantry', 'hit'): [
        "{attacker} synchronized their fire, striking {target} for {damage} damage.",
        "A well-placed shot from {attacker} hit {target} squarely, dealing {damage} damage.",
        "{attacker} advanced while firing, catching {target} out of position for {damage} damage."
    ],
    ('Infantry', 'Infantry', 'critical'): [
        "{attacker} executed a perfect flanking maneuver, devastating {target} for {damage}!",
        "A pinpoint headshot from {attacker} stunned {target}, dealing {damage} massive damage!",
        "{attacker} overran {target}'s position with overwhelming force, dealing {damage}!"
    ],

    ('Infantry', 'Armour', 'miss'): [
        "{attacker} fired their small arms at {target}, but the bullets just bounced off the thick plating.",
        "{attacker} tried to disable {target}'s treads, but missed completely.",
        "{target} rumbled forward, ignoring {attacker}'s futile attempts to strike."
    ],
    ('Infantry', 'Armour', 'hit'): [
        "{attacker} targeted a weak spot in {target}'s rear plating for {damage} damage.",
        "An anti-tank grenade from {attacker} exploded against {target}, dealing {damage} damage.",
        "{attacker} managed to damage {target}'s external sensors, dealing {damage} damage."
    ],

    ('Infantry', 'Air', 'miss'): [
        "{attacker} fired wildly into the sky, but {target} was far too fast.",
        "{target} performed a barrel roll, easily evading {attacker}'s ground fire.",
        "{attacker} couldn't get a proper lead on the fast-moving {target}."
    ],
    ('Infantry', 'Air', 'hit'): [
        "{attacker} scored a lucky hit on {target}'s fuselage for {damage} damage.",
        "A concentrated volley from {attacker} peppered {target}, dealing {damage} damage.",
        "{attacker} managed to clip {target}'s wing, dealing {damage} damage."
    ],

    # --- ARMOUR ATTACKING ---
    ('Armour', 'Infantry', 'hit'): [
        "{attacker} unleashed a coaxial machine gun burst upon {target}, dealing {damage} damage.",
        "A high-explosive shell from {attacker} detonated near {target} for {damage} damage.",
        "{attacker} forced {target} out of cover with heavy fire, dealing {damage} damage."
    ],
    ('Armour', 'Armour', 'hit'): [
        "{attacker} fired a sabot round directly into {target}'s hull for {damage} damage.",
        "The heavy cannons of {attacker} thundered, striking {target} for {damage} damage.",
        "Armor-piercing shells from {attacker} tore into {target}, dealing {damage} damage."
    ],
    ('Armour', 'Armour', 'critical'): [
        "{attacker} scored a direct hit on {target}'s ammo rack! {damage}!",
        "A devastating shot from {attacker} bypassed {target}'s reactive armor for {damage}!",
        "{attacker} pulverized {target}'s turret with a perfectly aimed shot, dealing {damage}!"
    ],
    ('Armour', 'Any', 'miss'): [
        "{attacker}'s main gun barked, but the shell kicked up dirt far from {target}.",
        "{attacker} suffered a targeting computer glitch and fired wide of {target}.",
        "{target} maneuvered quickly, causing {attacker}'s heavy shell to whistle past harmlessly."
    ],

    # --- AIR ATTACKING ---
    ('Air', 'Infantry', 'hit'): [
        "{attacker} strafed {target} with 20mm cannons, dealing {damage} damage.",
        "Cluster munitions from {attacker} rained down on {target} for {damage} damage.",
        "{attacker} dived from the clouds, catching {target} in the open for {damage} damage."
    ],
    ('Air', 'Armour', 'hit'): [
        "{attacker} launched a Maverick missile, striking {target} for {damage} damage.",
        "{attacker} strafed {target} for {damage} damage.",
        "A precision strike from {attacker} pierced {target}'s top armor for {damage} damage."
    ],
    ('Air', 'Air', 'hit'): [
        "{attacker} locked on and fired a Sidewinder, hitting {target} for {damage} damage.",
        "In a high-stakes dogfight, {attacker} got on {target}'s tail and dealt {damage} damage.",
        "{attacker} peppered {target} with autocannon fire in a passing sweep, dealing {damage} damage."
    ],
    ('Air', 'Any', 'critical'): [
        "{attacker} delivered a devastating payload directly onto {target}, dealing {damage}!",
        "{attacker} achieved a perfect target lock, obliterating {target}'s defenses for {damage}!",
        "A spectacular explosion rocked {target} as {attacker}'s strike hit home for {damage}!"
    ],

    # --- STATIC ATTACKING ---
    ('Static', 'Any', 'hit'): [
        "The fortified positions of {attacker} opened fire on {target}, dealing {damage} damage.",
        "{attacker} unleashed a steady stream of defensive fire, striking {target} for {damage} damage.",
        "{target} walked right into {attacker}'s kill zone, taking {damage} damage."
    ],

    # --- SPECIAL FORCES ATTACKING ---
    ('Special Forces', 'Any', 'hit'): [
        "{attacker} emerged from the shadows to strike {target} for {damage} damage.",
        "A precision sabotage operation by {attacker} damaged {target} for {damage} damage.",
        "{attacker} used advanced tactics to bypass {target}'s guard, dealing {damage} damage."
    ],
    ('Special Forces', 'Any', 'critical'): [
        "{attacker} executed a flawless assassination strike on {target}, dealing {damage}!",
        "{target} never saw {attacker} coming; a lethal strike dealt {damage}!",
        "{attacker} exploited a critical vulnerability in {target}, dealing {damage}!"
    ],

    # --- FALLBACKS ---
    ('Any', 'Any', 'miss'): [
        "{attacker} attacks {target} but misses!",
        "{attacker} fired at {target}, but the shot went wide.",
        "{target} successfully evaded {attacker}'s attack.",
        "{attacker} failed to find a target in {target}."
    ],
    ('Any', 'Any', 'graze'): [
        "{attacker} grazes {target} for {damage} damage. ({target} HP: {target_hp}/{target_max_hp})",
        "{attacker} scored a glancing blow on {target}, dealing {damage} damage. ({target} HP: {target_hp}/{target_max_hp})",
        "{target} took {damage} light damage from {attacker}'s attack. ({target} HP: {target_hp}/{target_max_hp})"
    ],
    ('Any', 'Any', 'hit'): [
        "{attacker} strikes {target} for {damage} damage! ({target} HP: {target_hp}/{target_max_hp})",
        "{attacker} hit {target} for {damage} damage. ({target} HP: {target_hp}/{target_max_hp})",
        "{target} took {damage} damage from {attacker}. ({target} HP: {target_hp}/{target_max_hp})"
    ],
    ('Any', 'Any', 'critical'): [
        "Critical hit! {attacker} strikes {target} for {damage}! ({target} HP: {target_hp}/{target_max_hp})",
        "{attacker} landed a devastating blow on {target}, dealing {damage}! ({target} HP: {target_hp}/{target_max_hp})",
        "A massive strike from {attacker} hit {target} for {damage}! ({target} HP: {target_hp}/{target_max_hp})"
    ],
}

def get_battle_log(attacker_name, attacker_type, target_name, target_type, hit_type, damage, target_hp, target_max_hp):
    """
    Selects and formats a battle log message based on the combat datasheet.
    """
    # Try specific match
    keys = [
        (attacker_type, target_type, hit_type),
        (attacker_type, 'Any', hit_type),
        ('Any', target_type, hit_type),
        ('Any', 'Any', hit_type)
    ]

    templates = []
    for key in keys:
        if key in BATTLE_LOG_TEMPLATES:
            templates = BATTLE_LOG_TEMPLATES[key]
            break

    if not templates:
        # Extreme fallback
        return f"{attacker_name} attacks {target_name} for {damage} damage ({hit_type})."

    template = random.choice(templates)
    
    # Style names
    # Attacker: Amber, Target: Blue
    s_attacker = f'<span class="text-amber-400 font-semibold">{attacker_name}</span>'
    s_target = f'<span class="text-blue-400 font-semibold">{target_name}</span>'

    # Format damage
    if hit_type == 'critical':
        # Critical hits get the red box with "Damage" included as previously requested
        display_damage = f'<span class="inline-block px-1.5 py-0.5 rounded bg-red-600 text-white font-bold mx-1">{damage} Damage</span>'
    else:
        # Other hits get red bold text for the number
        display_damage = f'<span class="text-red-500 font-bold">{damage}</span>'

    # Format HP numbers as well for extra flair
    s_hp = f'<span class="text-green-500 font-mono">{target_hp}</span>'
    s_max_hp = f'<span class="text-slate-400 font-mono">{target_max_hp}</span>'

    return template.format(
        attacker=s_attacker,
        target=s_target,
        damage=display_damage,
        target_hp=s_hp,
        target_max_hp=s_max_hp
    )
