"""Resource roles: which rol on which resource type grants which permissions.

Pure data, no imports: schemas, routes and ``core.authz`` all derive their
lists of valid types and rols from this one table.
"""

RESOURCE_ROLE_PERMISSIONS: dict[str, dict[str, set[str]]] = {
    "corpus_node": {
        "eigenaar": {
            "node:read",
            "node:update",
            "node:delete",
            "resource_permission:manage",
        },
        "betrokken": {"node:read", "node:update"},
        "adviseur": {"node:read"},
        "indiener": {"node:read"},
    },
    "initiatief": {
        "eigenaar": {
            "initiatief:read",
            "initiatief:update",
            "initiatief:delete",
            "resource_permission:manage",
        },
        "contributor": {"initiatief:read", "initiatief:update"},
        "viewer": {"initiatief:read"},
    },
    "lead": {
        "opdrachtgever": {"lead:read", "lead:update"},
        "contactpersoon": {"lead:read"},
        "betrokken": {"lead:read"},
    },
    "opdracht": {
        "eigenaar": {
            "opdracht:read",
            "opdracht:update",
            "opdracht:delete",
            "resource_permission:manage",
        },
        "betrokken": {"opdracht:read"},
        # Informational: the person is the client's contact, no access.
        "contactpersoon": set(),
    },
    "organisatie_eenheid": {
        "eigenaar": {"org:manage", "org:update", "resource_permission:manage"},
    },
}

# Every rol that exists on some resource type.
RESOURCE_ROLES: frozenset[str] = frozenset(
    rol for rols in RESOURCE_ROLE_PERMISSIONS.values() for rol in rols
)


def rols_of(resource_type: str) -> tuple[str, ...]:
    """The rols of *resource_type*, sorted (for ``Literal`` and error messages)."""
    return tuple(sorted(RESOURCE_ROLE_PERMISSIONS[resource_type]))
