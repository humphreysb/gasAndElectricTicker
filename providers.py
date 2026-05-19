"""Per-state utility provider registry.

The Ohio scraper queries the official Energy Choice marketplace by
TerritoryId. Each ID corresponds to a delivery utility. This module
maps those IDs to the friendly utility names used throughout the
dashboard.

As we add states, each one gets its own entry under STATES with its own
elec/gas mappings keyed by whatever ID convention that state's scraper
needs. Look up a state via `for_state(code)`.

Backward compatibility: `providers.elec` and `providers.gas` continue to
point at Ohio's mappings so existing callers keep working.
"""

STATES = {
    'OH': {
        'elec': {
            9: 'AES Power',
            2: 'AEP',
            4: 'Duke',
            7: 'Ohio Edison',
            6: 'Ilumminating Co',
            3: 'Toledo Edison',
        },
        'gas': {
            1: 'Enbridge-Dominion',
            11: 'Centerpoint',
            10: 'Duke',
            8: 'Columbia',
        },
    },
    'PA': {
        'elec': {
            1182: 'PECO Energy',
            1186: 'PPL Electric Utilities',
            1180: 'Duquesne Light',
            1181: 'Met-Ed',
            1183: 'Penelec',
            1184: 'Penn Power',
            1189: 'West Penn Power',
            1187: 'UGI',
        },
        'gas': {
            4425: 'UGI Utilities',
            4420: 'Columbia Gas of PA',
            4422: 'PECO Gas',
            4423: 'Peoples Natural Gas',
            4421: 'National Fuel Gas',
            4424: 'Philadelphia Gas Works (PGW)',
        },
    },
}


def for_state(state):
    """Return the dict-of-dicts ({'elec': ..., 'gas': ...}) for a state."""
    return STATES[state]


# --- Backward-compat shims ----------------------------------------------------
# Older callers (energy_scraper.py, build_dashboard.py) reference
# providers.elec and providers.gas directly. Keep those working by aliasing
# them to Ohio for now — the multi-state callers should use for_state().
elec = STATES['OH']['elec']
gas = STATES['OH']['gas']
