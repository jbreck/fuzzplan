#!/bin/bash
import re, sys, os, subprocess, random_types

class Fuzzplan :
    def closeBlock(self) :
        if len(self.currentBodyBlock) > 0 :
            self.bodyBlocks.append(self.currentBodyBlock)
            self.currentBodyBlock = list()
    def parseCommandFile(self, commandFilePath) :
        with open(commandFilePath,"r") as commandFile :
            self.header = list() # this is a list of strings
            self.footer = list() # this is a list of strings
            self.bodyBlocks = list() # this is a list of lists of strings
            self.currentBodyBlock = list()
            self.parameters = list()
            mode = "##body"
            for line in commandFile :
                sline = line.strip()
                if sline in ["##header","##body","##footer"] : 
                    mode = sline
                    self.closeBlock()
                elif sline.startswith "##param" :
                    parts = re.split("\s*",sline,maxsplit=2)
                    if len(parts) == 2 : self.parameters[parts[1]] = ""
                    elif len(parts) == 3 : self.parameters[parts[1]] = parts[2]
                    else : raise Exception("Malformed ##param line")
                elif mode == "##header" : header.append(line)
                elif mode == "##footer" : footer.append(line)
                else :
                    if len(sline) == 0 : self.closeBlock()
                    else: self.currentBodyBlock.append(line) 
            self.closeBlock()
            self.bodyBlocks.append(currentBodyBlock)
    def __init__(self, commandFilePath) : parseCommandFile(commandFilePath)
    def run(self) :
        pass

def usage() :
    print "USAGE: %s <command_file>"

def main() :
    if len(sys.argv) < 1 : 
        usage()
        sys.exit(0)
    commandFilePath = sys.argv[1]
    fuzzplan = Fuzzplan(commandFilePath)
    print "Beginning fuzzing:"
    fuzzplan.run()
