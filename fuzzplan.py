#!/usr/bin/python
import re, sys, os, subprocess, random, shlex, tempfile, stat
import default_substitution_types
import user_substitution_types

class Substitution :
    """This class represents an occurrence of a substitution point such as '@{alphanumeric}'"""
    def __init__(self, head, specific_params, fuzzplan) :
        self.head = head
        self.specific_params = specific_params
        self.fuzzplan = fuzzplan
        self.state = dict() # reserved for future use
        self.output = ""
        self.mutate() # this sets self.output, among other things
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

class CommandTemplate :
    """This class represents a template for a command, such as 'curl http://localhost/thing/@{numeric}/'"""
    def __init__(self, fuzzplan, string) :
        self.subs = dict()
        self.fuzzplan = fuzzplan
        self.string = string
        self.output = string
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
        subPointRegex = r"@\{([^}]+)\}"
        lastIndex = 0
        self.output = ""
        # Look for substitution points in self.string
        for iSub, match in enumerate(re.finditer(subPointRegex, self.string)) :
            if iSub not in self.subs :
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
                    self.subs[iSub] = Substitution(head, params, self.fuzzplan)
                else :
                    # no parameters
                    head = label.strip()
                    params = dict() # the user supplied no parameters at this substitution point
                    self.subs[iSub] = Substitution(head, params, self.fuzzplan)
            replacement = self.subs[iSub].getOutput()
            # Add a chunk of literal string, followed by the replacement
            self.output += self.string[lastIndex:match.start()] + str(replacement)
            lastIndex = match.end()
            # Now look for another substitution point
            match = re.search(subPointRegex, self.string)
        self.output += self.string[lastIndex:len(self.string)]

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
    def getIntParam(self, name) : return int(self.parameters[name])
    def getStringParam(self, name) : return self.parameters[name]
    def closeBlock(self) :
        if len(self.currentBodyBlock) > 0 :
            self.bodyBlocks.append(self.currentBodyBlock)
            self.currentBodyBlock = list()
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
    def newCommandBlock(self) :
        fuzzplan = self
        blockPlan = random.choice(self.bodyBlocks)
        newBlock = list()
        for commandTemplate in blockPlan :
            newBlock.append(CommandTemplate(fuzzplan, commandTemplate))
        return newBlock
    def newCommandSequence(self) :
        fuzzplan = self
        bodySequence = list()
        for i in range(self.getIntParam("nCommands")) :
            bodySequence.append(self.newCommandBlock())
        headerBlock = list()
        for commandTemplate in self.header :
            headerBlock.append(CommandTemplate(fuzzplan, commandTemplate))
        footerBlock = list()
        for commandTemplate in self.footer :
            footerBlock.append(CommandTemplate(fuzzplan, commandTemplate))
        self.commandBlocks = [headerBlock] + bodySequence + [footerBlock]
    def mutateCommandSequence(self) :
        if random.random() > 0.50 :
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
        outputValues = dict()
        # Scan the output printed by the script for lines of the form:
        #    ALL_CAPS_TEXT:=...anything...
        # These are output values produced by the script
        for line in stdout.split("\n") :
            print line.rstrip()
            matches = re.match("([A-Z0-9_]+):=(.*)", line)
            if matches :
                outputValues[matches.group(1)] = matches.group(2)
        if "OBJECTIVE" in outputValues :
            # The value of this OBJECTIVE output could be used to guide the fuzzing
            print "Fuzzplan sees that OBJECTIVE is:" + outputValues["OBJECTIVE"]
        # Delete the script file
        os.remove(scriptPath)
    def run(self) :
        self.newCommandSequence()
        iTrial = 1
        print "====== Executing fuzzing plan"
        while True :
            print "======== TRIAL %d" % iTrial
            self.mutateCommandSequence()
            self.execute()
            if iTrial == self.getIntParam("nTrials") : break
            iTrial += 1

def usage() :
    print "USAGE: %s <fuzzing_plan_file>"

def main() :
    if len(sys.argv) < 2 :
        usage()
        sys.exit(0)
    planFilePath = sys.argv[1]
    fuzzplan = Fuzzplan(planFilePath)
    fuzzplan.run()

if __name__=="__main__" : main()
