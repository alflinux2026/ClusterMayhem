def choose_leader(candidates):
    # menor priority gana
    return sorted(candidates, key=lambda x: x.priority)[0]