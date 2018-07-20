#!/usr/bin/python
import re, sys, os, subprocess, random, shlex, tempfile, stat, copy
import default_substitution_types
import user_substitution_types
from simanneal import Annealer

subPointRegex = r"@\{([^}]+)\}"

class Substitution :
    """This class represents an occurrence of a substitution point such as '@{alphanumeric}'"""
    def __init__(self, head=None, specific_params=None, fuzzplan=None, orig=None) :
        if orig is not None : # copy
            self.head = orig.head
            self.specific_params = copy.deepcopy(orig.specific_params)
            self.fuzzplan = orig.fuzzplan
            self.state = copy.deepcopy(orig.state)
            self.output = orig.output
        elif head is not None and specific_params is not None and fuzzplan is not None : # new
            self.head = head
            self.specific_params = specific_params
            self.fuzzplan = fuzzplan
            self.state = dict() # reserved for future use
            self.output = ""
            self.mutate() # this sets self.output, among other things
        else :
            raise Exception("Please pass head,specific_params,fuzzplan  or  orig  to Substitution")
    def mutate(self) :
        # This method calls a function whose name is self.head + "_random" within the
        #   user_substitution_types module, and, failing that, the default_substitution_types module.
        function_name_rand = self.head + "_random"
        if not hasattr(user_substitution_types, function_name_rand) :
            if not hasattr(default_substitution_types, function_name_rand) :
                raise Exception("Unrecognized substitution point with head: " + self.head)
            function = getattr(default_substitution_types, function_name_rand)
        else :
            function = getattr(user_substitution_types, function_name_rand)
        params = dict()
        # Allow the user to set plan-wide default parameters, by adding a line
        #   to their plan file such as "##intparam numeric.max 100".
        # These plan-wide defaults can still be overridden at any substitution point
        #   by writing something like "@{numeric max=200}"
        for p in self.fuzzplan.parameters :
            # Look for and apply any such plan-wide defaults that have been set:
            if p.startswith(self.head + ".") : params[p[len(self.head)+1:]] = self.fuzzplan.parameters[p]
        params.update(self.specific_params) # Bring in params from this substitution point specifically 
        params["fuzzplan"] = self.fuzzplan
        params["lastOutput"] = self.output 
        params["state"] = self.state # Make self.state visible to the mutation function
        self.output = function(params)
        self.state = params["state"] # Allow mutation function to change self.state
    def getOutput(self) : return self.output
    def setOutput(self, output) : self.output = output
    def setState(self, state) : self.state = state

def newSubstitutionFromMatch(match, fuzzplan) :
    # If the substitution point is "@{numeric min=0 max=100}", then the
    #  label is "numeric min=0 max=100"
    #  head is "numeric"
    #  kvp is "min=0 max=100"
    label = match.group(1)
    if " " in label :
        head = label[:label.index(" ")]
        kvp = label[label.index(" ")+1:]                
        # https://stackoverflow.com/questions/4764547/creating-dictionary-from-space-separated-key-value-string-in-python
        params = dict(token.split('=') for token in shlex.split(kvp))
        return Substitution(head, params, fuzzplan)
    else :
        # no parameters
        head = label.strip()
        params = dict() # the user supplied no parameters at this substitution point
        return Substitution(head, params, fuzzplan)

def newSubstitutionFromString(s,fuzzplan) :
    match = re.match(subPointRegex,s)
    return newSubstitutionFromMatch(match, fuzzplan)

class CommandTemplate :
    """This class represents a template for a command, such as 'curl http://localhost/thing/@{numeric}/'"""
    def __init__(self, fuzzplan=None, string=None, orig=None) :
        if orig is not None : # copy
            self.subs = dict()
            for kSub, vSub in orig.subs.items() : self.subs[kSub] = Substitution(orig=vSub)
            self.fuzzplan = orig.fuzzplan
            self.string = orig.string
            self.output = orig.output
        elif fuzzplan is not None and string is not None : # new
            self.subs = dict()
            self.fuzzplan = fuzzplan
            self.string = string
            self.output = string
        else :
            raise Exception("Please pass fuzzplan,string  or  orig  to  CommandTemplate")
    def getOutput(self) : 
        self.performSubstitutions()
        return self.output
    def getSubs(self) : return self.subs
    def setSubs(self, subs) : self.subs = subs
    def mutate(self) :
        sub = random.choice(self.subs)
        sub.mutate()
    def performSubstitutions(self) :
        # This regular expression matches things like @{alphanumeric} or @{numeric}
        lastIndex = 0
        self.output = ""
        # Look for substitution points in self.string
        for iSub, match in enumerate(re.finditer(subPointRegex, self.string)) :
            if iSub not in self.subs :
                self.subs[iSub] = newSubstitutionFromMatch(match, self.fuzzplan)
            replacement = self.subs[iSub].getOutput()
            # Add a chunk of literal string, followed by the replacement
            self.output += self.string[lastIndex:match.start()] + str(replacement)
            lastIndex = match.end()
            # Now look for another substitution point
            match = re.search(subPointRegex, self.string)
        self.output += self.string[lastIndex:len(self.string)]

class CommandSequence :
    def __init__(self, fuzzplan=None, orig=None) :
        if orig is not None :
            self.fuzzplan = orig.fuzzplan
            self.commandBlocks = list()
            for vBlock in orig.commandBlocks :
                commandBlock = list()
                for vCommand in vBlock :
                    commandBlock.append(CommandTemplate(orig=vCommand))
                self.commandBlocks.append(commandBlock)
            self.outputValues = copy.deepcopy(orig.outputValues)
        elif fuzzplan is not None :
            self.fuzzplan = fuzzplan
            self.outputValues = dict()
            self.newCommandSequence()
    def newCommandBlock(self) :
        blockPlan = random.choice(self.fuzzplan.bodyBlocks)
        newBlock = list()
        for commandTemplate in blockPlan :
            newBlock.append(CommandTemplate(self.fuzzplan, commandTemplate))
        return newBlock
    def newCommandSequence(self) :
        bodySequence = list()
        for i in range(self.fuzzplan.getIntParam("nCommands")) :
            bodySequence.append(self.newCommandBlock())
        headerBlock = list()
        for commandTemplate in self.fuzzplan.header :
            headerBlock.append(CommandTemplate(self.fuzzplan, commandTemplate))
        footerBlock = list()
        for commandTemplate in self.fuzzplan.footer :
            footerBlock.append(CommandTemplate(self.fuzzplan, commandTemplate))
        self.commandBlocks = [headerBlock] + bodySequence + [footerBlock]
    def mutateCommandSequence(self) :
        if random.random() < self.fuzzplan.getFloatParam("fuzzProbMutateSubstitution") :
            commandsContainingSubstitutions = list()
            for iBlock in range(len(self.commandBlocks)) :
                for iCommand in range(len(self.commandBlocks[iBlock])) :
                    if len(self.commandBlocks[iBlock][iCommand].getSubs()) > 0 :
                        commandsContainingSubstitutions.append( (iBlock,iCommand) )
            if len(commandsContainingSubstitutions) > 0 :
                # Pick a command that has a substitution point
                iBlock, iCommand = random.choice(commandsContainingSubstitutions)
                # Mutate just that one substitution point of that one command
                self.commandBlocks[iBlock][iCommand].mutate()
                return
        if len(self.commandBlocks) == 0 :
            self.commandBlocks.append(self.newCommandBlock())
            return
        # Could also opt to change length, swap command positions, etc.
        # Entirely replace the i^{th} command block
        # (Except, don't replace block 0 (the header) or the final block (the footer)
        i = random.choice(range(1,len(self.commandBlocks)-1))
        self.commandBlocks[i] = self.newCommandBlock()
    def execute(self) :
        scriptFile = tempfile.NamedTemporaryFile(delete=False)
        scriptPath = scriptFile.name
        # Write our commands into the script file:
        for block in self.commandBlocks :
            for command in block : 
                print >>scriptFile, command.getOutput()
        scriptFile.close()
        #https://stackoverflow.com/questions/12791997/how-do-you-do-a-simple-chmod-x-from-within-python
        os.chmod(scriptPath, os.stat(scriptPath).st_mode | stat.S_IEXEC)
        # Finally, we actually run the script:
        child = subprocess.Popen([scriptPath],stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)
        stdout, stderr = child.communicate()
        self.outputValues = dict()
        # Scan the output printed by the script for lines of the form:
        #    ALL_CAPS_TEXT:=...anything...
        # These are output values produced by the script
        for line in stdout.split("\n") :
            print line.rstrip()
            matches = re.match("([A-Z0-9_]+):=(.*)", line.rstrip())
            if matches :
                self.outputValues[matches.group(1)] = matches.group(2)
        os.remove(scriptPath)
    def getOutputValue(self, key) :
        if key not in self.outputValues : return None
        return self.outputValues[key]

class Fuzzplan :
    """This class represents a plan for how to fuzz the input to some application"""
    def __init__(self, planFilePath) :
        self.setDefaultParameters()
        self.parsePlanFile(planFilePath)
        self.commandBlocks = list()
    def setDefaultParameters(self) :
        self.parameters = dict()
        self.parameters["nCommands"] = 20
        self.parameters["nTrials"] = -1 # loop forever
        self.parameters["numeric.min"] = 0
        self.parameters["numeric.max"] = 1000000000
        self.parameters["alpha.len"] = 20
        self.parameters["alphanumeric.len"] = 20
        self.parameters["mode"] = "random"
        self.parameters["nMutants"] = 5
        self.parameters["fuzzProbMutateSubstitution"] = 0.5
        self.parameters["expr.binaryChars"] = "+-*/"
        self.parameters["expr.leaves"] = "@{numeric}" # separate with ;;
        self.parameters["expr.newProbLeaf"] = 0.6
        self.parameters["expr.left"] = "( "
        self.parameters["expr.right"] = " )"
        self.parameters["expr.mutProbLeaf"] = 0.2
        self.parameters["expr.mutProbTree"] = 0.1
        self.parameters["expr.childWeight"] = 1.5
    def getFloatParam(self, name) : return float(self.parameters[name])
    def getIntParam(self, name) : return int(self.parameters[name])
    def getStringParam(self, name) : return self.parameters[name]
    def closeBlock(self) :
        if len(self.currentBodyBlock) > 0 :
            self.bodyBlocks.append(self.currentBodyBlock)
            self.currentBodyBlock = list()
    def makeSubstitutionFromString(self, s) :
        return newSubstitutionFromString(s, self)
    def parsePlanFile(self, planFilePath) :
        with open(planFilePath,"r") as commandFile :
            self.header = list() # this is a list of strings
            self.footer = list() # this is a list of strings
            self.bodyBlocks = list() # this is a list of lists of strings
            self.currentBodyBlock = list()
            mode = "##body"
            for line in commandFile :
                sline = line.strip()
                if sline in ["##header","##body","##footer"] :
                    mode = sline
                    self.closeBlock()
                elif (sline.startswith("##intparam") 
                   or sline.startswith("##stringparam") 
                   or sline.startswith("##floatparam")):
                    parts = re.split("\s*",sline,maxsplit=2)
                    if len(parts) == 2 : self.parameters[parts[1]] = ""
                    elif len(parts) == 3 : 
                        convert = {"##intparam":int, 
                                   "##stringparam":str,
                                   "##floatparam":float,
                                  }[parts[0].strip()]
                        self.parameters[parts[1]] = convert(parts[2].strip())
                    else : raise Exception("Malformed ##param line")
                elif mode == "##header" : self.header.append(line)
                elif mode == "##footer" : self.footer.append(line)
                else :
                    if len(sline) == 0 : self.closeBlock()
                    else: self.currentBodyBlock.append(line)
            self.closeBlock()
           
    def run(self) :
        sequence = CommandSequence(self)
        iTrial = 1
        print "====== Executing fuzzing plan"
        while True :
            print "======== TRIAL %d" % iTrial
            if self.getStringParam("mode") == "random" :
                sequence.mutateCommandSequence()
                sequence.execute()
            elif self.getStringParam("mode") == "guided" :
                bestMutant = sequence
                bestObjective = sequence.getOutputValue("OBJECTIVE")
                for iMutant in range(self.getIntParam("nMutants")) :
                    mutant = CommandSequence(orig=sequence) # copy our sequence
                    mutant.mutateCommandSequence()
                    mutant.execute()
                    objective = mutant.getOutputValue("OBJECTIVE")
                    try :
                        if bestObjective is None or float(objective.strip()) > float(bestObjective.strip()) :
                            bestMutant = mutant
                            bestObjective = objective
                    except : pass # in case a weird objective value was returned
                sequence = bestMutant
            else :
                raise Exception("Unrecognized mode: " + self.getStringParam("mode"))
            # Could add an annealing mode here...

            if iTrial == self.getIntParam("nTrials") : break
            iTrial += 1
            
    def seq(self) :
        sequence = CommandSequence(self)
        return sequence
            
class anneal_fuzz(Annealer):
# state is the diff and the energy is the min distance
	def __init__(self, state):
		super(anneal_fuzz, self).__init__(state)  # important!
	
	def move(self):
		curr = self.state
		curr.mutateCommandSequence()
		self.state = curr
	
	def energy(self):
		seq = self.state
		seq.execute()
		objective = -float(seq.getOutputValue("OBJECTIVE"))
		return objective

def usage() : print "USAGE: %s <fuzzing_plan_file>"

def main() :
	if len(sys.argv) < 2 :
		usage()
		sys.exit(0)
	planFilePath = sys.argv[1]
	fuzzplan = Fuzzplan(planFilePath)
	init = fuzzplan.seq()
	af = anneal_fuzz(init)
	af.steps = fuzzplan.getIntParam("nTrials")
	af.copy_strategy = "deepcopy"
	state, e = af.anneal()
	print(state, -e)
    
   
if __name__=="__main__" : main()
