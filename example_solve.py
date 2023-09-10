from solver import Solver

verbose = False

# add attempted crew to this list as strings
att_crew = [
#'Bajoran Dukat', 'Sisko, The Emissary'
]

player_json = 'player.json'
# create a solver, defaults to UNM
s = Solver(player_json=player_json, diff='unm' ,min_portal=2, max_portal=5, req_lexico=True)

# solve the chain with these attempted crew
s.solve(att_crew, verbose=verbose)