"""Server-side, deny-by-default permissions, checked inside each transaction."""

from aeies.database.queries import rows


class Denied(ValueError):
    pass


def require(connection, actor, permission, department=None, level=None):
    roles = rows(
        connection,
        "SELECT * FROM admin_roles WHERE profile_id=%s AND active FOR SHARE",
        (actor,),
    )
    for role in roles:
        if role["role"] == "super":
            return
        if permission == "roles":
            continue
        if permission not in role["permissions"]:
            continue
        if role["department_id"] is not None and role["department_id"] != department:
            continue
        if role["level_id"] is not None and role["level_id"] != level:
            continue
        return
    raise Denied("You do not have permission for this action or academic scope.")


def require_student(connection, actor):
    from aeies.database.queries import one

    profile = one(connection, "SELECT * FROM profiles WHERE id=%s", (actor,))
    if not profile or not profile["full_name"]:
        raise Denied("Please complete /register before accessing resources.")
    return profile
