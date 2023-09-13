import json
from collections import Counter

class Node():
    def __init__(self, node:dict, id:int) -> None:
        self.id = id  # use id to ensure the hashing is unique
        self._traits:list = node['open_traits'].copy()
        self._traits.extend(node['hidden_traits'])
        self._nunknown:int = len(node['hidden_traits'])
        self.nknown:int = len(node['open_traits'])  # track both because _nunknown changes as node is solved
        self.solved:bool = False if '?' in self._traits else True
        self.poss_tsets = None if self.solved else []
        self.poss_traits = None if self.solved else set()
        self.force_print:bool = False
        self._iknown_lexico:int = -1  # index into known traits of element which determines lexicographical ordering
    
    def __hash__(self):
        return hash(str(self.id) + str(self.given_traits))
    
    def __eq__(self, other):
        if type(self) == type(other):
            return self.id == other.id and all(self._traits == other._traits)
        else:
            return False
    
    def __str__(self):
        return 'Node: ' + str(self._traits)

    def __len__(self):
        return len(self._traits)
    
    def __contains__(self, trait:str):
        if self.solved:
            return False
        return trait in self.poss_traits and not trait in self.known_traits
    
    def __getitem__(self, idx):
        return self._traits[idx]

    @property
    def hidden_traits(self):
        return self._traits[len(self.traits)-self._nunknown:]
    
    @property
    def known_traits(self):
        return self._traits[:len(self.traits)-self._nunknown]
    
    @property
    def given_traits(self):
        return self._traits[:self.nknown]
    
    @property
    def traits(self):
        return self._traits
    
    def print(self, inode:int, tt:dict):
        """prints the node header info

        Args:
            inode (int): integer label to print with node data
            tt (dict): translation dictionary to match the game client trait names
        """
        print('')
        #print(f'Node {inode} - ' + ('Partial Solution - ' if (self._iknown_lexico<-1 and '?' in self.hidden_traits) else ''), end='[' + ', '.join([tt[x] for x in self.known_traits]) if self.known_traits else '')
        print(f'Node {inode} - [' + ', '.join([tt[x] for x in self.given_traits]) + ']', end='')
        for trait in self._traits[self.nknown:]:
            translated_trait = trait if trait == '?' else tt[trait]
            print(' + ' + translated_trait, end='')
        print('')

    def build_poss_tsets(self, hidden_traits:list, lexico:bool=True):
        if self.solved:
            self.poss_tsets = None
            return 

        # initialize to empty list
        self.poss_tsets = []
        self.poss_traits = set()
        
        # handle 1 unknown trait and 2 unknown traits differently
        if self._nunknown == 1:
            self._add_1unknown_poss_tsets(hidden_traits, lexico)
        elif self._nunknown == 2:
            self._add_2unknown_poss_tsets(hidden_traits, lexico)
        
        # clean up the poss traits set
        for trait in self.known_traits:
            if trait in self.poss_traits:
                self.poss_traits.remove(trait)
        
    def _add_1unknown_poss_tsets(self, hidden_traits:list, lexico:bool):
        used_traits = []    

        for trait in hidden_traits:
            if trait in used_traits:
                continue
            else:
                used_traits.append(trait)
            if lexico:
                # str does lexicographical comparison by default
                if trait < self.known_traits[self._iknown_lexico]:
                    continue
            tset = self.known_traits.copy()
            tset.append(trait)
            tset = tuple(sorted(tset))
            self.poss_tsets.append(tset)
            self.poss_traits.add(trait)
    
    def _add_2unknown_poss_tsets(self, hidden_traits:list, lexico:bool):
        # for 2 unknown traits, have to make sure duped traits don't get added together, so track separately
        for i, trait1 in enumerate(hidden_traits):
            for j in range(i+1, len(hidden_traits)):
                trait2 = hidden_traits[j]
                if trait1 == trait2:
                    continue  # no crew has duped traits
                if lexico:
                    if trait1 < self.known_traits[self._iknown_lexico] or trait2 < self.known_traits[self._iknown_lexico]:
                        continue
                tset = self.known_traits.copy()
                tset.extend([trait1, trait2])
                tset = tuple(sorted(tset))
                if tset not in self.poss_tsets:
                    self.poss_tsets.append(tset)
                    self.poss_traits.add(trait1)
                    self.poss_traits.add(trait2)

    def remove_tried_tsets(self, att_crew:list, trait_db):
        """remove trait sets of attempted crew

        algorithm removes trait sets by iterating over the possible tsets and checking
        against the traitdb to see if any of the attempted crew match that tset

        Args:
            att_crew (list): list of strings of attempted crew
            trait_db (_type_): trait database to check crew against
        """
        iset_to_del = []
        for iset, tset in enumerate(self.poss_tsets):
            if tset in trait_db:
                for crew in att_crew:
                    if crew in trait_db[tset]:
                        iset_to_del.append(iset)
                        break
        
        for iset in sorted(iset_to_del, reverse=True):
            del self.poss_tsets[iset]
    
    def set_solved(self, tset:tuple):
        self.solved = True
        self.force_print = True
        ind = 0
        for itrait, trait in enumerate(self._traits):
            if trait == '?':
                self._traits[itrait] = tset[ind]
                ind += 1
        
        # ensure lexicographical sorting
        self._traits.sort()
    
    def set_trait(self, trait_to_set:str)->bool:
        set_solved = False
        for itrait, trait in enumerate(self._traits):
            if trait == '?':
                self._traits[itrait] = trait_to_set
                self._nunknown -= 1

                if self._nunknown > 0:
                    # move the lexicographical pointer since the other trait need not come after this trait
                    self._iknown_lexico -= 1
                else:
                    self.set_solved(self._traits)
                    set_solved = True

                return set_solved

    def update_poss_traits(self):
        poss_traits = set()
        for tset in self.poss_tsets:
            poss_traits.update(tset[-self._nunknown:])
        self.poss_traits = list(poss_traits)


class ComboChain():
    def __init__(self, json_file:str='player.json', diff:int=6) -> None:
        self._json_file = json_file
        self._json = None
        self._nodes:dict[Node, list] = {}
        self._hidden_traits:list[str] = []
        self.req_traits:dict = {}
        self.solution_ids:list[int] = []

        self._load_json(diff)
        self._build_nodes_from_json()
        self._get_hidden_traits()
        self._get_required_traits()

    def __iter__(self):
        for k in self._nodes.keys():
            yield k

    def __getitem__(self, idx):
        return self._nodes[idx]
    
    def __setitem__(self, idx, val):
        # don't allow creation of nodes
        if idx in self._nodes:
            self._nodes[idx] = val
    
    def items(self):
        return self._nodes.items()
    
    def __len__(self):
        return len(self._nodes)
    
    def _load_json(self, diff:int):
        with open(self._json_file,'rb') as f:
            data = json.load(f)

        # now just grab the combo chain info
        for boss in data['fleet_boss_battles_root']['statuses']:
            if boss['desc_id'] == diff:
                self._json = boss['combo']
                break

    def _build_nodes_from_json(self):
        for i,node in enumerate(self._json['nodes']):
            self._nodes[Node(node, i)] = []  # initialize value to empty list of crew
            if len(node)>2:
                self.solution_ids.append(node['unlocked_crew_archetype_id']) 

    def _get_required_traits(self):
        hid_traits = self._json['traits']
        vis_traits = []
        for node in self._json['nodes']:
            vis_traits.extend(node['open_traits'])
        
        req_traits = []
        # loop over all the hidden traits and gather the dupes
        for trait in hid_traits:
            if hid_traits.count(trait) > 1:
                req_traits.append(trait)
            elif trait in vis_traits:
                req_traits.append(trait)
        
        # mark off the ones already used
        for node in self._nodes:
            for used_trait in node.hidden_traits:
                if used_trait in req_traits:
                    req_traits.remove(used_trait)

        # store counts in the dict
        for trait in req_traits:
            if trait not in self.req_traits:
                self.req_traits[trait] = req_traits.count(trait)
        
    def _get_hidden_traits(self, keep_used:bool=False):
        self._hidden_traits = self._json['traits'].copy()
        if keep_used:
            return
        for node in self._json['nodes']:
            for hid_trait in node['hidden_traits']:
                if hid_trait != '?':
                    self._hidden_traits.remove(hid_trait)
    
    def build_poss_tsets(self, lexico:bool=True):
        for node in self._nodes:
            node.build_poss_tsets(self._hidden_traits, lexico=lexico)
    
    def remove_tried_tsets(self, att_crew:list, trait_db):
        for node in self._nodes:
            if not node.solved:
                node.remove_tried_tsets(att_crew, trait_db)
    
    def remove_set_traits(self, trait_list:list[str]):
        # subtract counters to get final counts
        list_cnt = Counter(self._hidden_traits)
        upd_cnt = Counter(trait_list)
        list_cnt.subtract(upd_cnt)

        # turn counts into an actual list
        new_hid_traits = []
        for trait in list_cnt:
            new_hid_traits.extend([trait]*list_cnt[trait])
        
        self._hidden_traits = new_hid_traits
        
        # now poll the nodes to see if poss_tsets can be eliminated
        for trait in trait_list:
            # make sure there aren't dupes left before eliminating
            if trait not in self._hidden_traits:
                # loop over nodes to find tsets to delete
                for node in self._nodes:
                    if node.solved:
                        continue
                    traits_to_remove = []
                    tsets_to_remove = []
                    # if the trait is a known trait, then nothing will be deleted
                    if trait in node.known_traits:
                        continue

                    # collect the traits and tsets, then delete AFTER
                    if trait in node.poss_traits:
                        traits_to_remove.append(trait)
                    for tset in node.poss_tsets:
                        if trait in tset:
                            tsets_to_remove.append(tset)
                    
                    node.poss_traits = [ t  for t in node.poss_traits if t not in traits_to_remove ]
                    node.poss_tsets = [ t  for t in node.poss_tsets if t not in tsets_to_remove ]
    
    def update(self, solutions:[list[tuple[tuple[str]]]])->bool:
        inode = 0
        reduced_poss_tsets = False
        for node in self._nodes:
            # need to see if the eliminated tsets actually reduced the trait pool
            old_poss_tsets = node.poss_tsets.copy()
            if node.solved:
                continue
            node.poss_tsets = []
            for soln in solutions:
                if soln[inode] not in node.poss_tsets:
                    node.poss_tsets.append(soln[inode])

            inode += 1
            diff = [ True for x in old_poss_tsets if x not in node.poss_tsets]
            reduced_poss_tsets |= any(diff)
        
        return reduced_poss_tsets