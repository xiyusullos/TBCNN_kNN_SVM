# -*- coding: utf-8 -*-
"""
Created on Mon Jun  9 14:46:46 2014

@author: mou
"""

import numpy as np

def InitParam(OldWeights, num = None, newWeights = None, upper = None, lower = None):

    oldlen = len(OldWeights)    
    # if newWeights != None:
    if newWeights is not None:
        newWeights = np.array(newWeights)
        num = len(newWeights)
        OldWeights = np.concatenate((OldWeights, newWeights.reshape(-1) ))
        
    else:
        if upper == None:
            upper = 0.0002
            lower = - 0.0002
        tmpWeights = np.random.uniform(lower, upper, num)
        OldWeights = np.concatenate((OldWeights, tmpWeights.reshape(-1) ))
    return OldWeights,range(oldlen, oldlen + num)


if __name__ == '__main__':
    Weights = []
    Weights, idx1 = InitParam(Weights, 10 )
    Weights, idx2 =  InitParam(Weights, 5)
    Weights, idx3 = InitParam(Weights, newWeights=[1,2,3])
    #print idx1
    #print idx2
    #print Weights
