import json

from combo_chain import ComboChain
from traitdb.sttcrew import TraitSetDB
from copy import deepcopy
from collections import Counter
# from crew_battle_actions import CrewBattleActionDB, CrewBattleAction

class Solver():

    '''
    A class to solve a combo chain given a trait set database
    '''
    boss_to_id = { 'easy':(1,1,2,2,4), 'normal':(2,1,3,2,4), 'hard':(3,1,4,2,4), 'brutal':(4,1,4,2,4), 'nm':(5,1,5,3,4), 'unm':(6,1,5,3,4)}
    def __init__(self, player_json:str='player.json', crew_json:str='crew.json', diff:str='unm', min_portal:int=2, max_portal:int=5, inc_non_portal:bool=True, req_lexico:bool=True) -> None:
        """Initializer for FBB combo chain solver

        Args:
            traitdb (TraitSetDB): the trait set database to solve against
            combo_chain (ComboChain): the combo chain from player.json
            min_portal (int, optional): minimum number of matching portal crew for a valid trait set. Defaults to 2.
            max_portal (int, optional): maximum number of matching portal crew for a valid trait set. Defaults to 5.
            inc_non_portal (bool, optional): add matching non-portal crew to the solution lists. Defaults to True.
            req_lexico (bool, optional): require lexicographical ordering of the traits. Defaults to True.
        """
        self.diff, self.min_stars, self.max_stars, self.min_set_size, self.max_set_size = self.boss_to_id[diff]
        self._traitdb = TraitSetDB(nmin=self.min_set_size, nmax=self.max_set_size, maxrarity=self.max_stars, add_portal_only=True, crewfile=crew_json)  # copies let us manipulate the db without destroying the originals
        self._chain = ComboChain(player_json, self.diff)
        self._lexico = req_lexico
        self._matching_crew:list[dict] = [] 
        self._opt_crew:list[dict] = []
        self._poss_solutions:list[list] = []
        self._node_solutions:list[str] = []
        self.niters:int = 0
        self.maxiters:int = 10
        self.nportal:(tuple) = (min_portal, max_portal)
        self._load_trait_translation()

        # finalize the trait db
        self._traitdb.prune_nodes(min_portal, del_all_greater=False)
        self._traitdb.prune_nodes(max_portal, del_all_greater=True)
        if inc_non_portal:
            self._traitdb.load_nonportals()
        
        # grab all the crew that already solved a node to add to attempted crew list
        if self._chain.solution_ids:
            self._node_solutions.extend(self._traitdb.get_solved_node_crew(self._chain.solution_ids))
    
    def print_settings(self, att_crew:list[str]):
        """Print the solver settings for sharing"""
        print('FBB Chain Solver Settings')
        print(f' o Lexicographical ordering: {self._lexico}')
        print(' o # Portal crew required: {}-{}'.format(*self.nportal))
        if att_crew:
            print('Attempted crew: ' + ', '.join(att_crew))
    
    def _load_trait_translation(self, fname='translation_en.json'):
        with open(fname, 'rb') as f:
            self._trait_translation = json.load(f)
        self._trait_translation = self._trait_translation['trait_names']
    
    def solve(self, att_crew:list[str]=[], verbose=False):
        """solve the combo chain
        """

        # start by building all possible tsets
        chain = self._chain
        chain.build_poss_tsets(lexico=self._lexico)

        if self._node_solutions:
            att_crew.extend(self._node_solutions)
        if att_crew:
            chain.remove_tried_tsets(att_crew, self._traitdb)
        
        keep_going = True
        while (keep_going):
            #print('-', end='')
            print('-'*30+'\n')
            keep_going = False
            if verbose:
                for i,node in enumerate(chain,start=1):
                    node.print(i, self._trait_translation)
                    print(node.poss_tsets)
            keep_going |= self._check_against_traitdb(verbose=verbose)
            if verbose: print('\n-----\njust checked against trait db')

            keep_going |= self._analyze_required_traits(verbose=verbose)
            if verbose: print('\n-----\njust analyzed required traits')
            
            keep_going |= self._check_nodes_for_guaranteed_traits(verbose=verbose)
            if verbose: print('\n-----\njust checked for guaranteed to be used traits')

            if not keep_going:
                if verbose: print('\n-----\nchecking full solutions!')
                keep_going |= self._check_full_solutions()

            self.niters += 1
            if self.niters > self.maxiters:
                print(f'\nIteration #{self.niters}')
                break
            else:
                pass
                #self._check_against_traitdb()
                #for i,node in enumerate(chain,start=1):
                #    node.print(i, self._trait_translation)
                #    print(node.poss_tsets)

                # maybe rebuild poss traits and tsets here for next round?
        
        print('\nDone solving. Finding matching crew...')
        self._build_crew_lists()
        print('Simplifying the matching crew lists')
        self._simplify_crew_lists()

        print('Done.')
        
        self.print_settings(att_crew)
        self.print_solution()
    
    def _check_full_solutions(self)->bool:
        """
        Check for consistency of possible trait sets across all nodes
        """
        made_changes = False

        poss_tsets = []
        istart = []
        for node in self._chain:
            if not node.solved:
                poss_tsets.append(node.poss_tsets)
                istart.append(len(node.known_traits))
            # else:
            #     poss_tsets = tuple(node.traits[-len(node.given_traits):])
            #     istart.append(len(node.given_traits))
        
        # now we have all the poss tsets in a nicely iterable data structure (list of lists)
        combs = self._generate_all_combinations(poss_tsets, istart)
        valid_solns, made_changes = self._check_solutions(combs)
        if made_changes:  # the solution checked eliminated some trait sets, but did it actually simplify?
            made_changes = self._chain.update(valid_solns)

        return False
        return made_changes
    
    def _generate_all_combinations(self, poss_tsets:list[list[tuple[str]]], istart:list[int])->list:
        potential_solns = []
        curr = []
        generate_combinations(poss_tsets, potential_solns, istart, 0, curr)
        return potential_solns
    
    def _check_solutions(self, potential_solns:list[str])->list[str]:
        """validate a list of potential solutions against the chain's required and hidden traits 

        Args:
            potential_solns (list[tuple[tuple[str]]]): _description_

        Returns:
            list[tuple[tuple[str]]]: _description_
        """
        made_changes = False
        valid_solns = []
        req_traits = self._chain.req_traits
        check_req_traits = sum(req_traits.values()) > 0
        for soln in potential_solns:
            keep = True
            cnt = Counter()
            # loop over the traits from each node and add to the counter
            for node in soln:
                cnt.update(node)
            
            # now check for validity
            for trait in cnt:
                if check_req_traits and trait in req_traits:
                    if cnt[trait] != req_traits[trait]:
                        made_changes = True
                        keep = False
                        break
                # not required, either 0/1 occurrences is valid
                elif trait not in req_traits and cnt[trait] > 1:
                    keep = False
                    made_changes = True
                    break
        
            if keep:
                valid_solns.append(soln)
        
        if not valid_solns:
            print('Required Traits:')
            print(self._chain.req_traits)
            print('\nPossible trait sets per node:', end='')
            for i,node in enumerate(self._chain,start=1):
                node.print(i, self._trait_translation)
                print(node.poss_tsets)
            raise RuntimeError('Could not find any solutions for this chain!')

        # nothing eliminated, we're done
        if not made_changes:
            return potential_solns, made_changes

        # add back the given traits for a full tset
        given_traits = []
        for node in self._chain:
            if not node.solved:
                given_traits.append(node.given_traits)
        
        valid_full_solns = []
        for soln in valid_solns:
            this_full_soln = []
            for given, hidden in zip(given_traits, soln):
                this_full_soln.append(tuple(given,)+hidden)
            valid_full_solns.append(this_full_soln)
        
        print(req_traits)
        for sol in valid_full_solns:
            print(sol)

        return valid_full_solns, made_changes

    def _check_against_traitdb(self, verbose:bool=False):
        """
        Check the possible tset list against those with possible solutions (crew)
        in the traitDB
        """
        made_changes = False
        for node in self._chain:
            if node.solved:
                continue
            node_changed = False
            tsets_to_remove = []
            for tset in node.poss_tsets:
                if tset not in self._traitdb:
                    tsets_to_remove.append(tset)
                    node_changed = True
            if node_changed:
                if verbose:
                    print('Based on traitDB lookup, removing the following trait sets:')
                    print(tsets_to_remove)
                node.poss_tsets = [t for t in node.poss_tsets if t not in tsets_to_remove]
                # rebuild the poss_traits
                made_changes = True
                node.update_poss_traits()
        
        return made_changes
    
    def _build_crew_lists(self):
        for node in self._chain:
            poss_crew = {}
            # for solved node just set to empty dict
            if node.solved:
                self._chain[node] = poss_crew
                continue
                
            # get crew list for unsolved node
            for tset in node.poss_tsets:
                if tset in self._traitdb:
                    # loop over all crew in the db with this trait set
                    for crew in self._traitdb[tset]:
                        traits = list(tset)
                        # traits is a list of the traits in this set
                        traits = [t for t in traits if t not in node.known_traits]
                        # now traits only contains the matching hidden traits
                        # add to this poss_crew's trait list
                        if crew in poss_crew:
                            num_tsets, set_of_matching_traits = poss_crew[crew]
                            num_tsets += 1
                            set_of_matching_traits.update(traits)
                            poss_crew[crew] = [num_tsets, set_of_matching_traits]
                        else:
                            poss_crew[crew] = [1, set(traits)]
            
            self._chain[node] = poss_crew
    
    def _simplify_crew_lists(self):
        for node, crew_traits_dict in self._chain.items():
            if node.solved:
                continue
            opt_crew = {}
            for crew, traits_count_and_set in crew_traits_dict.items():
                key = frozenset(traits_count_and_set[1])
                if key in opt_crew:
                    opt_crew[key].append(crew)
                else:
                    opt_crew[key] = [traits_count_and_set[0], crew]
        
            trait_lists = list(opt_crew.keys())
            for keys in trait_lists:
                # loop over the trait sets again to compare
                for keys2 in trait_lists:
                    if keys < keys2:
                    #if keys.strip('[]').split(',')[1] < keys2.strip('[]').split(',')[1]:  # strict subset, so will not delete itself
                        del opt_crew[keys]
                        break  # key is deleted, move on to next tset in outer loop

            self._chain[node] = opt_crew

    def _analyze_required_traits(self, verbose:bool=False):
        chain_updated = False
        req_traits_solved = []
        for req_trait, num_uses in self._chain.req_traits.items():
            # check which nodes have this trait in the poss_traits
            req_trait_by_node = [False]*len(self._chain)
            for node in self._chain:
                if req_trait in node:
                    req_trait_by_node[node.id] = True
            
            # now analyze full chain
            if num_uses>0 and req_trait_by_node.count(True) == num_uses:
                req_traits_solved.append(req_trait)
                # every node that has the req trait must use it
                if verbose:
                    print(f'Exactly {num_uses} node(s) can use {req_trait} - simplifying!')
                for modify, node in zip(req_trait_by_node, self._chain):
                    if modify:
                        chain_updated = True
                        if node.set_trait(req_trait):
                            # node was just solved
                            traits_to_remove = node[node.nknown:]
                            self._chain.remove_set_traits(traits_to_remove)
        
        # we used all of the required traits so update counter
        for trait in req_traits_solved:
            self._chain.req_traits[trait] = 0
                
        return chain_updated
    
    def _check_nodes_for_guaranteed_traits(self, verbose:bool=False):
        """
        check the nodes to see if they MUST use a particular trait
        based on the poss_tsets
        """
        chain_updated = False
        set_traits = []
        for node in self._chain:
            if node.solved:
                continue
            known_traits = node.known_traits  # do this lookup once and store
            for trait in node.poss_traits:
                if trait in known_traits:
                    continue
                for tset in node.poss_tsets:
                    if trait not in tset:
                        break
                else:
                    print(f'{node} must use {trait} given this list of possible trait sets:')
                    print(f'{node.poss_tsets}')
                    node.set_trait(trait)
                    chain_updated = True
                    set_traits.append(trait)
                    if trait in self._chain.req_traits:
                        self._chain.req_traits[trait] -= 1
        
        if set_traits:
            self._chain.remove_set_traits(set_traits)
        
        return chain_updated
    
    def print_solution(self):
        tt = self._trait_translation

        # print remaining traits that need to be used
        self.print_req_traits()

        for inode,(node, crew_and_trait_dict) in enumerate(self._chain.items(), start=1):
            # do we need to print this node?
            if node.solved and not node.force_print:
                continue
            node.print(inode, tt)

            # node is solved but not run yet
            if node.force_print:
                print( '1. ' + ', '.join(self._traitdb[tuple(node.traits)]))

            #spc = ' ' if len(crew_and_trait_dict) > 9 else ''
            # ^^ messes with Discord
            spc = '' if len(crew_and_trait_dict) > 9 else ''
            # sort crew by decreasing # of matching solutions
            for i,traits in enumerate(sorted(crew_and_trait_dict, key=lambda k:crew_and_trait_dict[k][0], reverse=True),start=1):
                if i == 10:
                    spc = ''
                print(spc + f'{i}. ' + ', '.join(crew_and_trait_dict[traits][1:]), end=': (')
                print(', '.join([tt[k] for k in sorted(traits)]), end=f') [{crew_and_trait_dict[traits][0]}]\n')
        
    def print_req_traits(self):
        """Print the required traits that still need to be used
        """
        if len(self._chain.req_traits) > 0:
            print('') 
        for trait,count in self._chain.req_traits.items():
            plural = 's' if count != 1 else ''
            print(f'{self._trait_translation[trait]} should be used {count} more time' + plural)

def generate_combinations(poss_tsets:list[list[tuple[str]]], combinations:list[tuple[tuple[str]]], istart:list[int], depth:int, curr:list[tuple[str]]):
    if depth == len(poss_tsets):
        # reach the end of the list of lists, add this combination
        combinations.append(tuple(curr))
        return
    
    # not at the end, add a tset and go one level deeper
    for set in poss_tsets[depth]:
        next = curr.copy()  # these are objects, so make copies, could probably pop as well
        next.append(set[istart[depth]:])
        generate_combinations(poss_tsets, combinations, istart, depth+1, next)