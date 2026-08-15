"""Regras puras de prontidão para missões autônomas do TurtleBot 4."""


def mission_readiness(checks: dict) -> dict:
    """Calcula a prontidão para iniciar uma missão autônoma.

    A prontidão de navegação direta exige LaserScan e AMCL frescos. Uma missão
    iniciada na dock tem outro contrato: ela própria executa o undock e só
    envia o primeiro goal depois de confirmar scan, odometria e TF. Quando o
    robô já está fora da dock, esses sinais frescos são obrigatórios.
    """
    required = [
        "create3_alive",
        "odom",
        "map",
        "navigate_to_pose",
        "global_costmap",
        "create3_dock_action",
        "create3_undock_action",
        "start_delivery",
        "stop_mission",
    ]
    start_mode = "docked" if checks.get("undocked") is False else "undocked"
    if start_mode == "undocked":
        required.extend(["scan", "amcl_pose"])

    missing = [name for name in required if checks.get(name) is not True]
    if not missing and start_mode == "docked":
        hint = (
            "Missão pronta para iniciar na dock. A rotina fará o undock e "
            "validará scan, odometria e TF antes do primeiro goal."
        )
    elif not missing:
        hint = "Missão pronta para iniciar com o robô fora da dock."
    else:
        hint = "Missão bloqueada pelos itens listados em mission_missing."

    return {
        "ready": not missing,
        "missing": missing,
        "required": required,
        "start_mode": start_mode,
        "hint": hint,
    }
