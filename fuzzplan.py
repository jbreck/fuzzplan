#!/usr/bin/python
import re, sys, os, subprocess, random, shlex, tempfile, stat
import user_substitution_types

class Fuzzplan :
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
                elif sline.startswith("##param"):
                    parts = re.split("\s*",sline,maxsplit=2)
                    if len(parts) == 2 : self.parameters[parts[1]] = ""
                    elif len(parts) == 3 : self.parameters[parts[1]] = parts[2].strip()
                    else : raise Exception("Malformed ##param line")
                elif mode == "##header" : header.append(line)
                elif mode == "##footer" : footer.append(line)
                else :
                    if len(sline) == 0 : self.closeBlock()
                    else: self.currentBodyBlock.append(line)
            self.closeBlock()
    def __init__(self, planFilePath) :
        self.setDefaultParameters()
        self.parsePlanFile(planFilePath)
    def callSubstitutionCommand(self, head, specific_params) :
        function_name_rand = head + "_random"
        if not hasattr(user_substitution_types, function_name_rand) :
            raise Exception("Unrecognized substitution point with head: " + head)
        function = getattr(user_substitution_types, function_name_rand)
        params = dict()
        # Allow the user to set plan-wide default parameters, by adding a line
        #   to their plan file such as "##param numeric.max 100".
        # These plan-wide defaults can still be overridden at any substitution point
        #   by writing something like "@{numeric max=200}"
        for p in self.parameters : 
            # Look for and apply any such plan-wide defaults that have been set:
            if p.startswith(head + ".") : params[p[len(head)+1:]] = self.parameters[p]
        params["fuzzplan"] = self
        params.update(specific_params) # Bring in params from this substitution point specifically 
        return function(params)
    def performSubstitutions(self, string) :
        # This regular expression matches things like @{alphanumeric} or @{numeric}
        subPointRegex = r"@\{([^}]+)\}"
        # Look for substitution points in string
        matches = re.search(subPointRegex, string)
        Z = 1
        while matches :
            # If the substitution point is "@{numeric min=0 max=100}", then the
            #  label is "numeric min=0 max=100"
            #  head is "numeric"
            #  kvp is "min=0 max=100"
            label = matches.group(1)
            if " " in label :
                head = label[:label.index(" ")]
                kvp = label[label.index(" ")+1]                
                # https://stackoverflow.com/questions/4764547/creating-dictionary-from-space-separated-key-value-string-in-python
                params = dict(token.split('=') for token in shlex.split(kvp))
                replacement = self.callSubstitutionCommand(head, params)
            else :
                # no parameters
                head = label.strip()
                params = dict() # the user supplied no parameters at this substitution point
                replacement = self.callSubstitutionCommand(head, params)
            # Actually perform the substitution
            #print "HI"
            #print " ~~> <" + string[matches.start():matches.end()] + ">"
            string = string[:matches.start()] + str(replacement) + string[matches.end():]
            #print "YO"
            #print string
            # Now look for another substitution point
            matches = re.search(subPointRegex, string)
            Z += 1
            if Z >= 5 : break
        return string
    def drawRandomSequence(self) :
        bodySequence = list()
        for i in range(self.getIntParam("nCommands")) :
            bodySequence += random.choice(self.bodyBlocks)
        sequence = self.header + bodySequence + self.footer
        substituted = list()
        for command in sequence :
            newCommand = self.performSubstitutions(command)
            substituted.append(newCommand)
        return substituted
    def execute(self, sequence) :
        scriptFile = tempfile.NamedTemporaryFile(delete=False)
        scriptPath = scriptFile.name
        # Write our commands into the script file:
        for command in sequence : print >>scriptFile, command
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
                outputValues[matches.group(1)]
        # Delete the script file
        os.remove(scriptPath)
    def run(self) :
        iTrial = 1
        print "====== Executing fuzzing plan"
        while True :
            print "======== TRIAL %d" % iTrial
            sequence = self.drawRandomSequence()
            self.execute(sequence)
            iTrial += 1
            if iTrial == self.getIntParam("nTrials") : break

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
