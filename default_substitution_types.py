import random

# REMEMBER: parameters set by the user could come in as strings,
#   so please convert them to the type that you expect.

def alphanumeric_random(params) :
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join([random.choice(chars) for I in range(int(params["len"]))])

def numeric_random(params) :
    return str(random.randint(int(params["min"]),int(params["max"])))

def float_random(params) :
    return str(random.uniform(float(params["min"]),float(params["max"])))

def weighted_choice(pairs) :
    totalWeight = 0.0
    for option, weight in pairs : 
        totalWeight += weight
    r = random.uniform(0.0, totalWeight)
    runningWeight = 0.0
    for option, weight in pairs : 
        runningWeight += weight
        if r <= runningWeight : return option

def expr_random(params) :
    binaries = [C for C in params["binaryChars"]]
    leaves = params["leaves"].split(";;")
    state = params["state"]
    fuzzplan = params["fuzzplan"]
    def new_leaf() :
        newLeafType = random.choice(leaves)
        return ["leaf",fuzzplan.makeSubstitutionFromString(newLeafType)]
    def new_subtree() :
        probLeaf = float(params["newProbLeaf"])
        if random.random() < probLeaf : return new_leaf()
        infix = random.choice(binaries)
        return ["infix",new_subtree(),infix,new_subtree()]
    def stringify(subtree) :
        if subtree[0] == "leaf" :
            return subtree[1].getOutput()
        if subtree[0] == "infix" :
            return (params["left"] + stringify(subtree[1]) + 
                    " " + subtree[2] + " " + 
                    stringify(subtree[3]) + params["right"])
        return "???"
    if "tree" not in state :
        tree = new_subtree()
        params["state"]["tree"] = tree
        return stringify(tree)
    def random_node(treeContainer) :
        if len(treeContainer) != 1 : raise Exception("Bad treeContainer in expr_random :: random_node")
        def collect_paths(subtree, path, collection, weight) :
            collection.append((path,weight))
            if subtree[0] == "leaf" : pass
            if subtree[0] == "infix" :
                collect_paths(subtree[1],path+[1],collection, weight*float(params["childWeight"]))
                collect_paths(subtree[3],path+[3],collection, weight*float(params["childWeight"]))
        weightedPaths = list()
        collect_paths(tree,[0],weightedPaths, 1.0)
        #for x,y in weightedPaths : print x,y
        randomPath = weighted_choice(weightedPaths)
        ORP = randomPath
        parent = treeContainer
        while len(randomPath) > 1 : 
            parent = parent[randomPath[0]]
            randomPath = randomPath[1:]
        def get() : return parent[randomPath[0]]
        def put(v) : 
            parent[randomPath[0]] = v
            #print "ORP=",ORP
        return {"get":get,"put":put}
    tree = params["state"]["tree"]
    probLeaf = float(params["mutProbLeaf"])
    probTree = float(params["mutProbTree"])
    r = random.random()
    treeContainer = [tree]
    n = random_node(treeContainer)
    if r < probLeaf :              n["put"](new_leaf())
    elif r < probLeaf + probTree : n["put"](new_subtree())
    else :
        import copy
        v = random_node([tree])
        n["put"](copy.deepcopy(v["get"]()))
    params["state"]["tree"] = treeContainer[0]
    return stringify(tree)
