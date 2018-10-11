import re

import constructNetwork_TBCNN as TC
import cPickle as p
from nn import serialize

import nn
import pycparser
from nn import FFNN
import sys, os

sys.path.append('../nn')
from pycparser import c_parser, c_ast, parse_file

from InitParam import *

import gl
from nn import Token
import numpy as np

sys.setrecursionlimit(1000000)

numFea = gl.numFea
numCon = gl.numCon

tokenMap = p.load(open(gl.tokenMap))
tokenNum = len(tokenMap)
numWords = len(tokenMap)
numDis = gl.numDis
numOut = gl.numOut

numPool = 3

np.random.seed(314)

preWeights = np.array([])
preBiases = np.array([])
preWeights, preWleft = InitParam(preWeights, num=numFea * numFea)
preWeights, preWright = InitParam(preWeights, num=numFea * numFea)
preBiases, preBtoken = InitParam(preBiases, num=numFea * tokenNum, upper=0.4, lower=0.6)
preBiases, preBconstruct = InitParam(preBiases, num=numFea)

preparam = p.load(open('../preparam'))
preW = preparam[:len(preWeights)]
preB = preparam[len(preWeights):]

preWleft = preW[preWleft]
preWright = preW[preWright]
preBtoken = preB[preBtoken]
preBconstruct = preB[preBconstruct]

#################################
##################################
# Initialize weights

Weights = np.array([])
Biases = np.array([])

# word/symbol/token embedding
Biases, BwordIdx = InitParam(Biases, newWeights=preBtoken)

# Biases, BwordIdx =  InitParam(Biases, len(preBtoken))
# left/right constructing and its biases
Weights, Wleft = InitParam(Weights, newWeights=preWleft)
Weights, Wright = InitParam(Weights, newWeights=preWright)
Biases, Bconstruct = InitParam(Biases, newWeights=preBconstruct)

'''

Biases, BwordIdx = InitParam(Biases, num=numFea*tokenNum, upper=0.4,lower=0.6)

        #Biases, BwordIdx =  InitParam(Biases, len(preBtoken))
        # left/right constructing and its biases
Weights, Wleft  = InitParam(Weights, num=numFea*numFea)
Weights, Wright = InitParam(Weights, num=numFea*numFea)
Biases,Bconstruct=InitParam(Biases,  num =numFea)


'''

# Weights, Wleft = InitParam(Weights,  len(preWleft) )
# Weights, Wright= InitParam(Biases,   len(preWright) )
# Biases, Bconstruct = InitParam(Biases, len(preBconstruct))

# combinition of the encoded vector and the vector of the symbol
w1 = (np.eye(numFea) / 2).reshape(-1)
w2 = (np.eye(numFea) / 2).reshape(-1)

Weights, Wcomb_ae = InitParam(Weights, newWeights=w1)
Weights, Wcomb_orig = InitParam(Weights, newWeights=w2)

# convolution
Weights, Wconv_root = InitParam(Weights, num=numFea * numCon)
Weights, Wconv_left = InitParam(Weights, num=numFea * numCon)
Weights, Wconv_right = InitParam(Weights, num=numFea * numCon)

Biases, Bconv = InitParam(Biases, num=numCon)

# discriminative layer
Weights, Wdis = InitParam(Weights, num=numPool * numCon * numDis)
Biases, Bdis = InitParam(Biases, num=numDis)

# output layer
Weights, Wout = InitParam(Weights, num=numDis * numOut, upper=.0002, lower=-.0002)
Biases, Bout = InitParam(Biases, newWeights=np.zeros((numOut, 1)))

Weights = Weights.reshape((-1, 1))
Biases = Biases.reshape((-1, 1))
# initial the gradients

gradWeights = np.zeros_like(Weights)
gradBiases = np.zeros_like(Biases)


def computeLeafNum(root, nodes, depth=0):
    if len(root.children) == 0:
        root.leafNum = 1
        root.childrenNum = 1
        return 1, 1, depth  # leafNum, childrenNum
    root.allLeafNum = 0
    avgdepth = 0.0
    for child in root.children:
        leafNum, childrenNum, childAvgDepth = computeLeafNum(nodes[child], nodes, depth + 1)
        root.leafNum += leafNum
        root.childrenNum += childrenNum
        avgdepth += childAvgDepth * leafNum
    avgdepth /= root.leafNum
    root.childrenNum += 1
    return root.leafNum, root.childrenNum, avgdepth


def InitByNodes(nodes):
    # add more infomation
    for nidx in xrange(len(nodes)):
        if nodes[nidx].parent != None:
            nodes[nodes[nidx].parent].children.append(nidx)

    # add infor of sibling
    for nidx in xrange(len(nodes)):
        if nodes[nidx].parent != None:
            nodes[nidx].siblings.extend(nodes[nodes[nidx].parent].children)  # appends all its children
            if nidx in nodes[nidx].siblings:
                nodes[nidx].siblings.remove(nidx)  # remove itself
    # add position info
    for nidx in xrange(len(nodes)):
        node = nodes[nidx]

        lenchildren = len(node.children)
        if lenchildren >= 0:
            for child in node.children:
                if lenchildren == 1:
                    nodes[child].leftRate = .5
                    nodes[child].rightRate = .5
                else:
                    nodes[child].rightRate = nodes[child].pos / (lenchildren - 1.0)
                    nodes[child].leftRate = 1.0 - nodes[child].rightRate

    dummy, dummy, avgdepth = computeLeafNum(nodes[-1], nodes)
    # print 'avgdepth', avgdepth
    avgdepth *= .6
    if avgdepth < 1:
        avgdepth = 1
    layers = TC.ConstructTreeConvolution(nodes, numFea, numCon, numDis, numOut, \
                                         Wleft, Wright, Bconstruct, \
                                         Wcomb_ae, Wcomb_orig, \
                                         Wconv_root, Wconv_left, Wconv_right, Bconv, \
                                         Wdis, Wout, Bdis, Bout, \
                                         poolCutoff=avgdepth
                                         )
    return layers


def ConstructNodes(ast, name, parent, pos, nodes, leafs):
    # global tmpCnt
    if name == None:
        name = ast.__class__.__name__
    # if name not in tmptokenMap.keys():
    #        tmptokenMap[name] = tmpCnt
    #        tmpCnt += 1
    if gl.reConstruct:
        if name == 'For' or name == 'While' or name == 'DoWhile':
            name = 'For'  # Loop (Consider For, While, DoWhile as For)
    Node = Token.token(name, gl.numFea * tokenMap[name], \
                       parent, pos)
    if len(ast.children()) == 0:
        leafs.append(Node)
    else:
        nodes.append(Node)
    # print nodes[0].word
    curid = len(nodes)
    for idx, (name, child) in enumerate(ast.children()):
        ConstructNodes(child, None, curid, idx, nodes, leafs)
        # def __init__(self, word, bidx, parent, pos = 0):


def AdjustOrder(nodes):
    nodes.reverse()
    length = len(nodes)
    for node in nodes:
        if node.parent != None:
            node.parent = length - node.parent


import func_defs


def GetMajorFunction(root):
    v = func_defs.FuncDefVisitor()
    v.visit(root)
    nodes = v.nodes;

    major = nodes[0]
    for cnode in nodes:
        if (major.NodeNum() < cnode.NodeNum()):
            major = cnode
    return major;


# text ='''int test{
# int x= 2+3;
# x= 10; for (int i=1; i<10; i++) x+=i;}
# '''
# parser = pycparser.c_parser.CParser()
# ast = parser.parse(text=text)
# c_ast.ignoreDecl = True
# ast.reConstruct()
#
# nodes = []
# leafs = []
# # print 'constructing the network'
# ConstructNodes(ast, 'root', None, None, nodes, leafs)
# nodes.extend(leafs)
# #print len(nodes)
# AdjustOrder(nodes)
#
# for nidx in xrange(len(nodes)):
#     if nodes[nidx].parent != None:
#         nodes[nodes[nidx].parent].children.append(nidx)
# for nidx in xrange(len(nodes)):
#     if nodes[nidx].parent != None:
#         nodes[nidx].siblings.extend(nodes[nodes[nidx].parent].children)  # appends all its children
#         if  nidx in nodes[nidx].siblings:
#             nodes[nidx].siblings.remove(nidx)  # remove itself
#
# for n in nodes:
#     sibinfo =''
#     for sib in n.siblings:
#         sibinfo = sibinfo + nodes[sib].word+'-'
#     print n.word,', siblings:', sibinfo
# ast.show()
# layers = InitByNodes(nodes)

def InitNetbyText(text=''):
# def InitNetbyText(text, filename='', debuglevel=0):
#     parser = pycparser.c_parser.CParser()
    ast = pycparser.parse_file(filename=text, use_cpp=True)  # Parse code to AST
    # ast = parser.parse(text, filename=filename, debuglevel=debuglevel)  # Parse code to AST
    # ast = pycparser.parse_file(filename=filename)
    if gl.reConstruct:  # reconstruct braches of For, While, DoWhile
        ast.reConstruct()

    nodes = []
    leafs = []
    # print 'constructing the network'
    ConstructNodes(ast, 'root', None, None, nodes, leafs)
    # print len(nodes)
    # print nodes[0].word
    nodes.extend(leafs)
    # print len(nodes)
    AdjustOrder(nodes)
    # print '---------------------------------------'
    for ii in xrange(len(nodes)):
        # print ii
        inode = nodes[ii]
        # print ii,'  ',inode.word,'  ',inode.parent,'  ',nodes[inode.parent].word,'  ',inode.pos
    layers = InitByNodes(nodes)

    return layers


if __name__ == "__main__":
    procount = 0;
    for subdir in os.listdir(gl.datadir):
        if not subdir.endswith('/'):
            subdir = subdir + '/'

        count = 0
        procount += 1
        print '!!!!!!!!!!!!!!!!!!  procount = ', procount
        # if procount >3:
        #    break
        for onefile in os.listdir(gl.datadir + subdir):

            # print 'oneoneoneoneone!!!!!!!!!! '
            filename = onefile
            onefile = gl.datadir + subdir + onefile
            try:
                # print '-----------------', onefile, '-----------------'
                # ast = parse_file(onefile, use_cpp=True)
                if onefile.endswith(".txt"):
                    instream = open(onefile, 'r')
                    text = instream.read()
                    text = text.replace('\r\n', '\n')
                    instream.close()

                    # layers = InitNetbyText(text=text)
                    layers = InitNetbyText(text=onefile)
                    # layers = InitNetbyText('', filename=onefile)

                    count += 1
                    # print 'count = ',count
                    if count > 500:
                        break

                    directory = gl.targetdir + subdir
                    if not os.path.exists(directory):
                        os.makedirs(directory)
                    serialize.serialize(layers, directory + '/seri_' + filename)

            except Exception as e:
                print '!!! error', e
                print 'ooooops, parsing error for', onefile
                continue

    print 'Done!!!!!!'
    print 'procount = ', procount
