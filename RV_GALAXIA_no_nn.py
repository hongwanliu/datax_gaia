# %%
"""
# ML to find radial velocities using GALAXIA sim withOUT Nearest Neighbors
"""

# %%
import matplotlib
import matplotlib.colors as colors

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
matplotlib.use('Agg')
import os.path
import sys
import gzip
import matplotlib.gridspec as gridspec
from scipy.stats import norm
import keras
from keras import backend as K

import argparse, ast
import tensorflow as tf
from tensorflow.keras import initializers
matplotlib.rcParams.update({'font.family':'cmr10','font.size': 13})
matplotlib.rcParams['axes.unicode_minus']=False
matplotlib.rcParams['axes.labelsize']=15
plt.rcParams['figure.figsize']=(4,4)
plt.rcParams['figure.dpi'] = 80
plt.rcParams['mathtext.fontset'] = 'cm'
plt.rcParams['mathtext.rm'] = 'serif'
plt.rcParams['xtick.direction'] = 'in'
plt.rcParams['ytick.direction'] = 'in'
plt.rcParams['xtick.top'] = True
plt.rcParams['ytick.right'] = True

# %%
#keras.__version__

# %%

parser = argparse.ArgumentParser()
parser.add_argument("--datafilepath_train", action="store", dest="datafilepath_train", default='/tigress/ljchang/DataXGaia/data/galaxia_mock/training_set_500k.npz', type=str)
parser.add_argument("--datafilepath_val", action="store", dest="datafilepath_val", default='/tigress/ljchang/DataXGaia/data/galaxia_mock/validation_set_500k.npz', type=str)
parser.add_argument("--datafilepath_test", action="store", dest="datafilepath_test", default='/tigress/ljchang/DataXGaia/data/galaxia_mock/test_set_500k.npz', type=str)
parser.add_argument("--use_cols", default = 'l,b,pmra,pmdec,parallax', type=str)
parser.add_argument("--nnodes", nargs="+", default = 30, type=int)
parser.add_argument("--ncores", action="store", dest="ncores", default=16, type=int)
parser.add_argument("--spec", action="store", dest="spec", default="new", type=str)
parser.add_argument("--weight_type", action="store", dest="weight_type", default="log2d", type=str)
parser.add_argument("--run_scan", action="store", dest="run_scan", default=True, type=ast.literal_eval)
parser.add_argument("--activation", action="store", dest="activation", default="tanh", type=str)

results = parser.parse_args()
datafilepath_train = results.datafilepath_train
datafilepath_val = results.datafilepath_val
datafilepath_test = results.datafilepath_test
use_cols = results.use_cols
nnodes = results.nnodes
ncores = results.ncores
spec = results.spec
weight_type = results.weight_type
run_scan = results.run_scan
activation = results.activation
print(datafilepath_train)
print(datafilepath_val)
print(datafilepath_test)
if spec != "new" and datafilepath_train == "/tigress/ljchang/DataXGaia/data/galaxia_mock/training_set_500k.npz":
    print("wrong input data for this spec")
    sys.exit()

print(use_cols)
# %%
config = tf.compat.v1.ConfigProto(intra_op_parallelism_threads=ncores, inter_op_parallelism_threads=ncores,  allow_soft_placement=True,device_count = {'CPU': ncores})
session = tf.compat.v1.Session(config=config)
K.set_session(session)

# %%
data_train = np.load(datafilepath_train)
data_val = np.load(datafilepath_val)
data_test = np.load(datafilepath_test)
if spec == "new":
    data_train = data_train['data']
    data_val = data_val['data']
    data_test = data_test['data']
else:
    data_train = data_train['arr_0']
    data_val = data_val['arr_0']
    data_test = data_test['arr_0']

# %%
data_cols = ['source_id', 'l', 'b', 'ra', 'dec', 'parallax', 'parallax_error', 
             'pmra', 'pmra_error', 'pmdec', 'pmdec_error', 'radial_velocity',
             'photo_g_mean_mag', 'photo_bp_mean_mag', 'photo_rp_mean_mag',
             'x','y','z','vx','vy','vz','r','phi','theta','vr','vphi','vtheta']


# %%
data_train = pd.DataFrame(data_train, columns=data_cols)
data_val = pd.DataFrame(data_val, columns=data_cols)
data_test = pd.DataFrame(data_test, columns=data_cols)

# %%
data_train.head()

# %%
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from scipy.interpolate import interp1d

# %%
l_train = (data_train['l']).values
l_val = (data_val['l']).values

vr_train = (data_train['radial_velocity']).values
vr_val = (data_val['radial_velocity']).values


# %%
#Laura's weights 
from scipy.interpolate import interp2d
from tqdm import tqdm
lbins2d = np.linspace(0,360,51)
vbins2d = np.linspace(-550,550,51)

lbins2d_centers = (lbins2d[1:]+lbins2d[:-1])/2
vbins2d_centers = (vbins2d[1:]+vbins2d[:-1])/2

counts2d_train = np.histogram2d(l_train,vr_train,bins=[lbins2d,vbins2d])[0]
counts2d_val = np.histogram2d(l_val,vr_val,bins=[lbins2d,vbins2d])[0]

if weight_type == "lin2d":
    invweight_func_train = interp2d(lbins2d_centers,vbins2d_centers,counts2d_train.T)
    invweight_func_val = interp2d(lbins2d_centers,vbins2d_centers,counts2d_val.T)

    invweights2d_train = np.zeros(len(l_train))
    invweights2d_val = np.zeros(len(l_val))

    for i in tqdm(range(len(l_train))):
        invweights2d_train[i] = invweight_func_train(l_train[i],vr_train[i])
    for j in tqdm(range(len(l_val))):
        invweights2d_val[j] = invweight_func_val(l_val[j],vr_val[j])

    weights_train = 1/invweights2d_train

    weights_val = 1/invweights2d_val

    print("Using linear weights in vr and l")

elif weight_type == "log2d":
    invweight_func_train = interp2d(lbins2d_centers,vbins2d_centers,counts2d_train.T)
    invweight_func_val = interp2d(lbins2d_centers,vbins2d_centers,counts2d_val.T)

    invweights2d_train = np.zeros(len(l_train))
    invweights2d_val = np.zeros(len(l_val))

    for i in tqdm(range(len(l_train))):
        invweights2d_train[i] = invweight_func_train(l_train[i],vr_train[i])
    for j in tqdm(range(len(l_val))):
        invweights2d_val[j] = invweight_func_val(l_val[j],vr_val[j])

    weights_train = 1/invweights2d_train
    weights_train = np.log(weights_train)
    weights_train = weights_train - np.min(weights_train) + 1

    weights_val = 1/invweights2d_val
    weights_val = np.log(weights_val)
    weights_val = weights_val - np.min(weights_val) + 1

    print("Using log weights in vr and l")

elif weight_type == "log1d":
    counts_train, bins_train = np.histogram(vr_train,bins=np.linspace(-700,700,51))
    bin_centers_train = (bins_train[1:]+bins_train[:-1])/2
    interp_func_train  = interp1d(bin_centers_train,(counts_train).astype('float'))
    inv_weights_train = interp_func_train(vr_train)
    weights_train = 1/inv_weights_train
    weights_train = np.log(weights_train)
    weights_train = weights_train - np.min(weights_train)+1

    counts_val, bins_val = np.histogram(vr_val,bins=np.linspace(-700,700,100))
    bin_centers_val = (bins_val[1:]+bins_val[:-1])/2
    interp_func_val  = interp1d(bin_centers_val,(counts_val).astype('float'))
    inv_weights_val = interp_func_val(vr_val)
    weights_val = 1/inv_weights_val
    weights_val = np.log(weights_val)
    weights_val = weights_val - np.min(weights_val)+1
    print("Using log weights in vr")

# %%
data_train['cos(l)'] = data_train['l'].apply(lambda x: np.cos(x))
data_train['sin(l)'] = data_train['l'].apply(lambda x: np.sin(x))
data_train['cos(b)'] = data_train['b'].apply(lambda x: np.cos(x))
data_train['sin(b)'] = data_train['b'].apply(lambda x: np.sin(x))


data_val['cos(l)'] = data_val['l'].apply(lambda x: np.cos(x))
data_val['sin(l)'] = data_val['l'].apply(lambda x: np.sin(x))
data_val['cos(b)'] = data_val['b'].apply(lambda x: np.cos(x))
data_val['sin(b)'] = data_val['b'].apply(lambda x: np.sin(x))


data_test['cos(l)'] = data_test['l'].apply(lambda x: np.cos(x))
data_test['sin(l)'] = data_test['l'].apply(lambda x: np.sin(x))
data_test['cos(b)'] = data_test['b'].apply(lambda x: np.cos(x))
data_test['sin(b)'] = data_test['b'].apply(lambda x: np.sin(x))



# %%
data_train.head()

# %%
data_cols = ['source_id', 'l', 'b', 'ra', 'dec', 'parallax', 'parallax_error', 
             'pmra', 'pmra_error', 'pmdec', 'pmdec_error', 'radial_velocity',
             'photo_g_mean_mag', 'photo_bp_mean_mag', 'photo_rp_mean_mag',
             'x','y','z','vx','vy','vz','r','phi','theta','vr','vphi','vtheta','cos(l)','sin(l)','cos(b)','sin(b)']

# %%
SS = StandardScaler()
mu = np.mean((data_train['radial_velocity']).values)
stddev = np.std((data_train['radial_velocity']).values)
data_train_scaled = SS.fit_transform(data_train)
data_val_scaled = SS.transform(data_val)
data_test_scaled = SS.transform(data_test)

# %%
data_train_scaled = pd.DataFrame(data_train_scaled, columns=data_cols)
data_val_scaled = pd.DataFrame(data_val_scaled, columns=data_cols)
data_test_scaled = pd.DataFrame(data_test_scaled, columns=data_cols)

# %%
print(use_cols)
use_cols = [str(i) for i in use_cols.split(',')]
dic = {'sinb':'sin(b)', 'cosb':'cos(b)', 'sinl':'sin(l)', 'cosl':'cos(l)'}
use_cols = [dic.get(n, n) for n in use_cols]
print(use_cols)
input_vars = ''
for elem_i in range(len(use_cols)):
    input_vars = str(input_vars) + list(use_cols[elem_i])[0]
print(input_vars)    
# Make the design matrix
X_train = data_train_scaled[use_cols].values
y_train = (data_train_scaled['radial_velocity']).values

X_val = data_val_scaled[use_cols].values
y_val = (data_val_scaled['radial_velocity']).values

X_test = data_test_scaled[use_cols].values
y_test = (data_test_scaled['radial_velocity']).values

# %%
from keras.models import Sequential
from keras.layers import Dense
from keras.callbacks import EarlyStopping, ModelCheckpoint
from keras.optimizers import Adam

# %%

from keras import callbacks as callbacks
global index 
import tensorflow as tf

# %%
def LikelihoodLossFunction(y_true, y_pred):
    # shape of y_pred should be (nsamples, 2)
    # the first column should be the mean of the prediction
    # the second column is the confidence (number of standard deviations)
#     print y_true.shape
#     print y_pred.shape
    SIGMA = K.abs(y_pred[:, 1]) + 1e-6

    LOC = y_pred[:, 0]
    
    X = y_true[:, 0]
    weights = y_true[:,1]
    ARG = K.abs(X - LOC) / (2 * K.abs(SIGMA))
    PREFACT = K.log(K.pow(2 * np.pi * K.square(SIGMA), -0.5))
    return K.mean((ARG - PREFACT) * weights)


# %%
def ConstantLikelihoodLossFunction(y_true, y_pred):
    # shape of y_pred should be (nsamples, 2)
    # the first column should be the mean of the prediction
    # the second column is the confidence (number of standard deviations)
#     print y_pred.shape
    LOC = y_pred[:,0]
    X = y_true[:, 0]
    weights = y_true[:,1]
    ARG = K.square(X - LOC) / (2.0)
    PREFACT = K.log(K.pow(2 * np.pi, -0.5))
    return K.mean((ARG - PREFACT) * weights)

# %%
"""
# Two network technique to calculate the error
"""

# %%
from sklearn.neighbors import NearestNeighbors
from keras.utils import Sequence
from keras.layers import Input, Dense, Lambda, Concatenate, Dropout, Activation, Add
from keras.models import Model
from keras.utils import plot_model
from IPython.display import clear_output
from keras.callbacks import ModelCheckpoint, EarlyStopping, ReduceLROnPlateau, CSVLogger

# %%
#y_low = -5
#y_high = 5
#bin_num = 100
#plt.hist((data_train_scaled['radial_velocity']).values, bins=bin_num, range=(y_low,y_high), histtype='step', edgecolor = 'purple', color= 'skyblue', label = 'vlos', alpha=0.5, density = True)
#plt.hist((data_train_scaled['radial_velocity']).values, weights = weights_train, bins=bin_num, range=(y_low,y_high), histtype='step', color= 'orange', label = 'weighted', density = True)
#plt.hist(-(data_train_scaled['radial_velocity']).values, bins=bin_num, range=(y_low,y_high), histtype='step', edgecolor = 'magenta', color= 'pink',  label = '-vlos', alpha = 0.5, density = True)
#plt.hist(-(data_train_scaled['radial_velocity']).values, weights = weights_train, bins=bin_num, range=(y_low,y_high), histtype='step', color= 'red', label = 'weighted', density = True)
#plt.legend(bbox_to_anchor=(1.05, 1))
#plt.title('train')


# %%
y_train = np.vstack([y_train, weights_train]).T
y_val = np.vstack([y_val, weights_val]).T

# %%
initializer = tf.keras.initializers.glorot_uniform(seed=1)
inputs = Input(shape=(len(use_cols),))
nlayers = nnodes
MeanEst = (Dense(nlayers, activation=activation, kernel_initializer=initializer))(inputs)
MeanEst = (Dropout(0.1))(MeanEst)
MeanEst = (Dense(nlayers, activation=activation, kernel_initializer=initializer))(MeanEst)
MeanEst = (Dropout(0.1))(MeanEst)
MeanEst = (Dense(nlayers, activation=activation, kernel_initializer=initializer))(MeanEst)
MeanEst = (Dropout(0.1))(MeanEst)
MeanEst = (Dense(nlayers, activation=activation, kernel_initializer=initializer))(MeanEst)
MeanEst = (Dropout(0.1))(MeanEst)
MeanEst = (Dense(1, activation='linear', kernel_initializer=initializer))(MeanEst)
MeanModel = Model(inputs=[inputs], outputs=MeanEst)

ConfEst= (Dense(nlayers, activation=activation, kernel_initializer=initializer))(inputs)
ConfEst = (Dropout(0.1))(ConfEst)
ConfEst= (Dense(nlayers, activation=activation, kernel_initializer=initializer))(ConfEst)
ConfEst = (Dropout(0.1))(ConfEst)
ConfEst= (Dense(nlayers, activation=activation, kernel_initializer=initializer))(ConfEst)
ConfEst = (Dropout(0.1))(ConfEst)
ConfEst= (Dense(nlayers, activation=activation, kernel_initializer=initializer))(ConfEst)
ConfEst = (Dropout(0.1))(ConfEst)
ConfEst= (Dense(1, activation='relu', kernel_initializer=initializer))(ConfEst)
ConfModel = Model(inputs=[inputs], outputs=ConfEst)

CombinedSub = Concatenate(axis=-1)([MeanModel(inputs), ConfModel(inputs)])

CombinedModel = Model(inputs=[inputs], outputs=CombinedSub)

# %%
CombinedModel.summary()

# %%
import os
num_samp = str(data_test.shape[0])
act_func = activation
neurons = 'D'+str(nnodes)
dropout = 'p1dropout_seed1'
lweights = weight_type
spec = spec
folder_name = 'G_train_2it_'+num_samp+'_'+act_func+'_'+neurons+'_'+dropout+'_'+input_vars+'_'+lweights+'_'+spec
filename = 'plots_test_2it_'+num_samp+'_'+act_func+'_'+neurons+'_'+dropout+'_'+input_vars+'_'+lweights+'_'+spec
print('saving to '+ folder_name)
if not os.path.exists('/tigress/dropulic/'+folder_name):
    os.makedirs(folder_name)
    os.makedirs(folder_name+'/models_GALAXIA_nonn')
    os.makedirs(folder_name+'/logs')
if (os.path.exists('/tigress/dropulic/'+folder_name) and not os.path.exists('/tigress/dropulic/'+folder_name+'/models_GALAXIA_nonn')):
    os.makedirs(folder_name+'/models_GALAXIA_nonn')
    os.makedirs(folder_name+'/logs')
"""
# %%
"""
## First training iteration
"""

# %%
CheckPoint = ModelCheckpoint(folder_name+'/models_GALAXIA_nonn/TrainingMean_{epoch:04d}.hdf5',
                             verbose=0,
                             save_best_only=False
                            )
ES = EarlyStopping(patience=40, verbose=True, restore_best_weights=True)
RLR = ReduceLROnPlateau(patience=10, min_lr=1e-5, verbose=True)
CSV_logger = CSVLogger(filename=folder_name+'/logs/training_mean.log', separator=',', append=False)

mycallbacks = [CheckPoint, ES, RLR, CSV_logger]
#mycallbacks = [ES, RLR]

# %%
ConfModel.trainable = False
MeanModel.trainable = True
CombinedModel.compile(loss=ConstantLikelihoodLossFunction,
                      optimizer='adam'
                     )
history = CombinedModel.fit(X_train,y_train,
                  validation_data=(X_val, y_val),
                  epochs=1000,
                  batch_size=10000,
                  callbacks = mycallbacks
                 )

# %%
plt.plot(history.history['loss'])
plt.plot(history.history['val_loss'])
plt.yscale('log')
plt.xlabel('Epochs')
plt.ylabel('Mean Model (Constant Loss Function)')
plt.legend(['Train', 'Validation'])
plt.show()

# %%
CheckPoint2 = ModelCheckpoint(folder_name+'/models_GALAXIA_nonn/TrainingErrorBars_{epoch:04d}.hdf5',
                             verbose=0,
                             save_best_only=False
                            )
ES2 = EarlyStopping(patience=40, verbose=True, restore_best_weights=True)
RLR2 = ReduceLROnPlateau(patience=10, min_lr=1e-5)
CSV_logger2 = CSVLogger(filename=folder_name+'/logs/training_errorbars.log', separator=',', append=False)

mycallbacks2 = [CheckPoint2, ES2, RLR2, CSV_logger2]
#mycallbacks2 = [ES2, RLR2]

# %%
ConfModel.trainable = True
MeanModel.trainable = False
CombinedModel.compile(loss=LikelihoodLossFunction,
                      optimizer='adam'
                     )

history = CombinedModel.fit(X_train,y_train,
                  validation_data=(X_val, y_val),
                  epochs=1000,
                  batch_size=10000,
                  callbacks = mycallbacks2
                 )

# %%
plt.plot(history.history['loss'])
plt.plot(history.history['val_loss'])
plt.yscale('log')
plt.xlabel('Epochs')
plt.ylabel('Confidence Model (Likelihood Loss Function)')
plt.legend(['Train', 'Validation'])
plt.show()

# %%
"""
## Second Training Iteration
"""

# %%
CheckPoint4 = ModelCheckpoint(folder_name+'/models_GALAXIA_nonn/TrainingMean2_{epoch:04d}.hdf5',
                             verbose=0,
                             save_best_only=False
                            )
ES4 = EarlyStopping(patience=40, verbose=True, restore_best_weights=True)
RLR4 = ReduceLROnPlateau(patience=10, min_lr=1e-5, verbose=True)
CSV_logger4 = CSVLogger(filename=folder_name+'/logs/training_mean2.log', separator=',', append=False)

mycallbacks4 = [CheckPoint4, ES4, RLR4, CSV_logger4]
#mycallbacks4 = [ES4, RLR4]

# %%
ConfModel.trainable = False
MeanModel.trainable = True
CombinedModel.compile(loss=ConstantLikelihoodLossFunction,
                      optimizer='adam'
                     )
history = CombinedModel.fit(X_train,y_train,
                  validation_data=(X_val, y_val),
                  epochs=1000,
                  batch_size=10000,
                  callbacks = mycallbacks4
                 )

# %%
plt.plot(history.history['loss'])
plt.plot(history.history['val_loss'])
plt.yscale('log')
plt.xlabel('Epochs')
plt.ylabel('Mean Model (2nd Train) (Constant Loss Function)')
plt.legend(['Train', 'Validation'])
plt.show()

# %%
CheckPoint5 = ModelCheckpoint(folder_name+'/models_GALAXIA_nonn/TrainingErrorBars2_{epoch:04d}.hdf5',
                             verbose=0,
                             save_best_only=False
                            )
ES5 = EarlyStopping(patience=40, verbose=True, restore_best_weights=True)
RLR5 = ReduceLROnPlateau(patience=10, min_lr=1e-5)
CSV_logger5 = CSVLogger(filename=folder_name+'/logs/training_errorbars2.log', separator=',', append=False)

mycallbacks5 = [CheckPoint5, ES5, RLR5, CSV_logger5]
#mycallbacks5 = [ES5, RLR5]

# %%
ConfModel.trainable = True
MeanModel.trainable = False
CombinedModel.compile(loss=LikelihoodLossFunction,
                      optimizer='adam'
                     )

history = CombinedModel.fit(X_train,y_train,
                  validation_data=(X_val, y_val),
                  epochs=1000,
                  batch_size=10000,
                  callbacks = mycallbacks5
                 )

# %%
plt.plot(history.history['loss'])
plt.plot(history.history['val_loss'])
plt.yscale('log')
plt.xlabel('Epochs')
plt.ylabel('Confidence Model (2nd Train) (Likelihood Loss Function)')
plt.legend(['Train', 'Validation'])
plt.show()

# %%
"""
## Train Both
"""

# %%
CheckPoint3 = ModelCheckpoint(folder_name+'/models_GALAXIA_nonn/TrainingBoth_{epoch:04d}.hdf5',
                             verbose=0,
                             save_best_only=False
                            )
ES3 = EarlyStopping(patience=40, verbose=True, restore_best_weights=True)
RLR3 = ReduceLROnPlateau(patience=10, min_lr=1e-5)
CSV_logger3 = CSVLogger(filename=folder_name+'/logs/training_both.log', separator=',', append=False)

mycallbacks3 = [CheckPoint3, ES3, RLR3, CSV_logger3]
#mycallbacks3 = [ES3, RLR3]

# %%
ConfModel.trainable = True
MeanModel.trainable = True
CombinedModel.compile(loss=LikelihoodLossFunction,
                      optimizer='adam'
                     )



# %%
history = CombinedModel.fit(X_train,y_train,
                  validation_data=(X_val, y_val),
                  epochs=1000,
                  batch_size=10000,
                  callbacks = mycallbacks3
                 )

# %%
plt.plot(history.history['loss'])
plt.plot(history.history['val_loss'])
#plt.yscale('log')
plt.xlabel('Epochs')
plt.ylabel('Both Models (Likelihood Loss Function)')
plt.legend(['Train', 'Validation'])
plt.savefig('Loss_Plot_Iterate.png')
plt.show()

# %%
CombinedModel.save_weights(folder_name+"/models_GALAXIA_nonn/ModelWeights.h5")
"""
# %%
"""
### Evaluate the Test Set
"""

# %%
CombinedModel.load_weights(folder_name+'/models_GALAXIA_nonn/' + 'ModelWeights.h5')
test_preds_2 = CombinedModel.predict(X_test)
y_low = -250
y_high = 250
#rescale test_preds_2
test_preds_2[:,0] = (test_preds_2[:,0] * stddev)+mu
test_preds_2[:,1] = (test_preds_2[:,1] * stddev)+mu

# %%
quant = np.quantile(test_preds_2[:,1], [0.01,0.05,0.1,0.25,0.5])
#quant = np.quantile(test_preds_2[:,1],[.01,.05])
rounded_quant = np.round(quant,2)
quant_string = []
for elem_i in range(len(rounded_quant)):
    p_elem = str(rounded_quant[elem_i])
    p_elem = p_elem.replace('.', 'p')
    quant_string.append(str(p_elem))

#need to define test_preds_arrays
sigma_arr_names = []
for elem_i in range(len(quant_string)):
    sigma_arr_names.append('test_preds_' + str(quant_string[elem_i]))

for elem_i in range(len(rounded_quant)):
    globals()[sigma_arr_names[elem_i]] = np.delete(test_preds_2, np.where(test_preds_2[:,1]>=rounded_quant[elem_i])[0], 0)


# %%
def save_indices(thresh, thresh_string):
    
    list_err_lt = []   
    list_err_lt = [(data_test['radial_velocity']).values[i] for i in range(len(test_preds_2[:,1])) if test_preds_2[i,1] < thresh]
    print(len(list_err_lt))
    #now need indices of these values in data
    indices = []
    if not os.path.exists('/tigress/dropulic/'+folder_name+'/data_indices_error_lt_'+thresh_string+'.npy'):
    	for i in range(len(list_err_lt)):
        	indices.append(data_test[data_test['radial_velocity']==(list_err_lt[i])].index[0])
    	np.save(folder_name+'/data_indices_error_lt_'+thresh_string,indices)
        

# %%
from scipy.stats import ks_2samp
from scipy.stats import kstest
from scipy.stats import f
from scipy.stats import gaussian_kde
from scipy.stats import norm
from scipy.optimize import curve_fit
from scipy.interpolate import interp1d
from scipy.integrate import quad

# %%
"""
## Going to use Monte Carlo simulations to predict errorbars. 
"""

# %%
def monte_carlo(df, test_preds_cut, thresh, thresh_string):  
    from matplotlib.colors import LogNorm
    mc_vr_pred_list = []
    resample_test_list = []
    bin_values_list = []
    min_array = []
    max_array = []
    min_array_r = []
    max_array_r = []
    min_array_th = []
    max_array_th = []
    min_array_phi = []
    max_array_phi = []

    data_test = reload_data_per_cut(thresh, thresh_string)
    hb_list = []
    hb_list_r = []
    hb_list_th = []
    hb_list_phi = []
    hex_centers = []
    
    bin_values_list_r = []
    bin_values_list_th = []
    bin_values_list_phi = []
    
    cdf_mc_list = []
    N = len((data_test['radial_velocity']).values)
    x_range = np.linspace(y_low,y_high,N)
    for mc_i in range(0,100):
        mc_vr_pred = []
        resample_test = []
        for star_i in range(0,len(test_preds_cut)):
            #print(test_preds_cut[star_i,1])
            mc_vr_pred.append(np.random.normal(test_preds_cut[star_i,0],test_preds_cut[star_i,1]))

        mc_vr_pred_list.append(mc_vr_pred)
        resample_test_list.append(resample_test)
        n, bins = np.histogram(mc_vr_pred,bins=50,range=(y_low,y_high), density = True)
        n_test_preds, bins_test_preds = np.histogram((data_test['radial_velocity']).values, bins=50, range=(y_low,y_high))
        cdf = np.cumsum(n_test_preds)
        cdf_mc_list.append(np.cumsum(n))
        
        plt.figure(2)
        hb = plt.hexbin((data_test['radial_velocity']).values, mc_vr_pred,gridsize=100, norm = LogNorm(),extent=[-200, 200, -200, 200]);
        hb_list.append(hb.get_array());
        bin_values_list.append(n)
        
        #now for the coordinate-transformed histograms
        vel_sph_coord = get_coord_transform(data_test, np.array(mc_vr_pred))
        n_r , bins_r = np.histogram(vel_sph_coord[:,0], bins=50, range=(-250,250))
        n_th , bins_th = np.histogram(vel_sph_coord[:,1], bins=50, range=(-250,250))
        n_phi , bins_phi = np.histogram(vel_sph_coord[:,2], bins=50, range=(-450,0))
        bin_values_list_r.append(n_r)
        bin_values_list_th.append(n_th)
        bin_values_list_phi.append(n_phi)
        
        
        hb_r = plt.hexbin((data_test['vr']).values, vel_sph_coord[:,0],gridsize=100, norm = LogNorm(),extent=[-250, 250, -250, 250]);
        hb_list_r.append(hb_r.get_array());
        
        
        hb_th = plt.hexbin((data_test['vtheta']).values, vel_sph_coord[:,1],gridsize=100, norm = LogNorm(),extent=[-250, 250, -250, 250]);
        hb_list_th.append(hb_th.get_array());
        
        
        hb_phi = plt.hexbin((data_test['vphi']).values, vel_sph_coord[:,2],gridsize=100, norm = LogNorm(),extent=[-450, 250, -450, 250]);
        hb_list_phi.append(hb_phi.get_array());
        plt.close(2)
    
    bin_values_list_arr = np.array(bin_values_list)    
    max_array = bin_values_list_arr.max(axis=0)
    median_array = np.median(bin_values_list_arr,axis=0)
    min_array = bin_values_list_arr.min(axis=0) 
    
    bin_values_list_r_arr = np.array(bin_values_list_r)    
    max_array_r = bin_values_list_r_arr.max(axis=0)
    min_array_r = bin_values_list_r_arr.min(axis=0) 
    
    bin_values_list_th_arr = np.array(bin_values_list_th)    
    max_array_th = bin_values_list_th_arr.max(axis=0)
    min_array_th = bin_values_list_th_arr.min(axis=0) 
    
    bin_values_list_phi_arr = np.array(bin_values_list_phi)    
    max_array_phi = bin_values_list_phi_arr.max(axis=0)
    min_array_phi = bin_values_list_phi_arr.min(axis=0) 

    return vel_sph_coord, min_array, max_array,median_array, hb_list, hb_list_r,hb_list_th,hb_list_phi, min_array_r,max_array_r,min_array_th,max_array_th, min_array_phi,max_array_phi, mc_vr_pred_list,cdf_mc_list


# %%
import TransformCoords
def get_coord_transform(df, train_preds):
    #needs only vr values of train_preds (maybe...need to see what to do about error)
    # m12i
    # v_LSR = [224.7092,-20.3801, 3.8954]
    # r_LSR = [0,8.2,0]
    # Galaxia
    v_LSR = [11.1, 239.08, 7.25]
    r_LSR = [-8.,0.,0.015]
    inds = np.arange(df.shape[0])
    inds_train = np.arange(df.shape[0])
    sub_num = df.shape[0]
    vels_sph = np.array([df['vr'].values[inds][:sub_num],df['vtheta'].values[inds][:sub_num],df['vphi'].values[inds][:sub_num]]).T
    coords_cart = np.array([df['x'].values[inds][:sub_num],df['y'].values[inds][:sub_num],df['z'].values[inds][:sub_num]]).T
    
    ra_cut = df['ra'].values[inds][:sub_num]
    dec_cut = df['dec'].values[inds][:sub_num]
    parallax_cut = df['parallax'].values[inds][:sub_num]
    pmra_cut = df['pmra'].values[inds][:sub_num]
    pmdec_cut = df['pmdec'].values[inds][:sub_num]
    rv_cut = df['radial_velocity'].values[inds][:sub_num]
    
    U_pred_train,V_pred_train,W_pred_train = TransformCoords.pm2galcart(np.deg2rad(ra_cut[inds_train]),np.deg2rad(dec_cut[inds_train]),parallax_cut[inds_train],pmra_cut[inds_train],pmdec_cut[inds_train],train_preds.flatten().astype('float'))
    
    coords_cart_train = coords_cart[inds_train,:]
    
    vels_cart_pred_train = np.array([U_pred_train+v_LSR[0],V_pred_train+v_LSR[1],W_pred_train+v_LSR[2]]).T
    
    coords_sph_train, vels_sph_pred_train = TransformCoords.rvcart2sph_vec(coords_cart_train,vels_cart_pred_train)
    
    coords_sph_train[:,[1,2]] = coords_sph_train[:,[2,1]] # Swap theta, phi into correct order
    
    vels_sph_pred_train[:,[1,2]] = vels_sph_pred_train[:,[2,1]] # Swap theta, phi into correct order
    
    return vels_sph_pred_train



# %%
def reload_data_per_cut(thresh, thresh_string):
    hold = 0
    data_test = np.load(datafilepath_test)
    if spec == "new": data_test = data_test['data']
    else: data_test = data_test['arr_0']
    data_cols = ['source_id', 'l', 'b', 'ra', 'dec', 'parallax', 'parallax_error', 
                 'pmra', 'pmra_error', 'pmdec', 'pmdec_error', 'radial_velocity',
                 'photo_g_mean_mag', 'photo_bp_mean_mag', 'photo_rp_mean_mag',
                 'x','y','z','vx','vy','vz','r','phi','theta','vr','vphi','vtheta']
    data_test = pd.DataFrame(data_test, columns=data_cols)
    indices_to_drop = []
    if thresh < 80 and thresh > 0:
        indices_to_drop = np.load(folder_name+'/data_indices_error_lt_'+thresh_string+'.npy')
        print(np.shape(indices_to_drop))
        data_test = data_test.loc[indices_to_drop]
    elif thresh == 0: 
        hold = 0
        print('hold = 0')

    weights_test = np.ones(data_test.shape[0])
    return data_test

# %%
def kl_div(p, q, bin_width):
    return sum(p[i]*bin_width * np.log2((p[i]*bin_width)/(q[i]*bin_width)) for i in range(len(p)))
def gaussian(x,mu,sigma):
    prefactor = 1/(np.sqrt(2*np.pi)*sigma)
    return prefactor*np.exp(-(x-mu)*(x-mu)/(2*sigma*sigma))
def chi_square(y_true, y_pred,sigma):
    chi_sq = sum((y_true-y_pred)*(y_true-y_pred)*(1/(sigma*sigma)))*(1/(len(y_true)-1))
    return chi_sq
def plot_test(thresh, thresh_string):
    data_test = reload_data_per_cut(thresh, thresh_string)
    print('shape of data_test is '+str(data_test.shape))
    if thresh == 0: test_preds = test_preds_2
    else:
        test_preds_name = 'test_preds_' + thresh_string
        test_preds = eval(test_preds_name)

    y_low = -250
    y_high = 250
    fig, ax = plt.subplots(nrows=6, ncols=3, sharex=False, sharey=False,figsize=(12,24))
    plt.subplots_adjust(wspace = 0.3, hspace = 0.3)
    from matplotlib.colors import LogNorm
    
    h1 = ax[1,0].hist2d(test_preds[:,1],test_preds[:,0], bins=40,norm = LogNorm())
    clb1 = plt.colorbar(h1[3],ax = ax[1,0])
    clb1.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    ax[1,0].set_ylabel(r'$v_{\rm{los}}^{\rm{pred}}$',labelpad=-10)
    ax[1,0].set_xlabel('$\sigma$',labelpad=-5)
    
    def coeff_determination(y_true, y_pred):
        SS_res =  sum(np.square( y_true-y_pred ))
        SS_tot = sum(np.square( y_true - np.mean(y_true) ) )
        return ( 1 - (SS_res/SS_tot)) 
    Rsquare = coeff_determination((data_test['radial_velocity']).values, test_preds[:,0])
    txt =('input vars = '+ str(use_cols)+ ', '+neurons+' '+num_samp+' '+act_func+' '+dropout+' '+lweights+' '+spec)
    if not os.path.exists('Rsquare_list.txt'):
        r_file= open("Rsquare_list.txt", "w")
        r_file.write("\n")
        if thresh == 0: r_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' R2 = '+str(Rsquare))
        else: r_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' R2 = '+str(Rsquare))
    else:
        with open("Rsquare_list.txt", "a") as r_file:
            r_file.write("\n")
            if thresh == 0: r_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' R2 = '+str(Rsquare))
            else: r_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' R2 = '+str(Rsquare))
    r_file.close()

    Xsquare = chi_square((data_test['radial_velocity']).values, test_preds[:,0], test_preds[:,1])
    if not os.path.exists('Xsquare_list.txt'):
        x_file= open("Xsquare_list.txt", "w")
        x_file.write("\n")
        if thresh == 0: x_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' X2 = '+str(Xsquare))
        else: x_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' X2 = '+str(Xsquare))
    else:
        with open("Xsquare_list.txt", "a") as x_file:
            x_file.write("\n")
            if thresh == 0: x_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' X2 = '+str(Xsquare))
            else: x_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' X2 = '+str(Xsquare))
    x_file.close()

    hb = ax[0,2].hexbin((data_test['radial_velocity']).values, test_preds[:,0],gridsize=100, norm = LogNorm(),extent=[-200, 200, -200, 200])
    x1 = np.linspace(-150,150,1000)
    y1 = x1
    ax[0,2].plot(x1,y1,'k--')
    ax[0,2].set_ylabel(r'$v_{\rm{los}}^{\rm{pred}}$',labelpad=-10)
    ax[0,2].set_xlabel(r'$v_{\rm{los}}^{\rm{meas}}$, R2='+str('%.3f'%(Rsquare))+', X2='+str('%.3f'%(Xsquare)))
    clb3 = plt.colorbar(hb,ax = ax[0,2])
    clb3.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)


    h2 = ax[1,2].hist2d((data_test['l']).values,test_preds[:,0], bins=40,norm = LogNorm(),rasterized=True)
    clb4 = plt.colorbar(h2[3], ax = ax[1,2])
    clb4.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    ax[1,2].plot(x1,y1,'k--')
    ax[1,2].set_xlabel(r'$l$',labelpad=-3)
    ax[1,2].set_ylabel(r'$v_{\rm{los}}^{\rm{pred}}$',labelpad=-5)


    dist_hist = np.divide(np.ones_like((data_test['parallax']).values),(data_test['parallax']).values)
    h3 = ax[2,0].hist2d(dist_hist, test_preds[:,1], bins=40, norm = LogNorm(),rasterized=True)
    clb5 = plt.colorbar(h3[3],ax = ax[2,0])
    clb5.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    ax[2,0].set_xlabel('Distance (kpc)',fontsize = 12)
    ax[2,0].set_ylabel('$\sigma$',labelpad=-5)

    plotrange = np.linspace(-5,5,1000)
    diff_hist = np.divide(np.subtract(test_preds[:,0],(data_test['radial_velocity']).values),test_preds[:,1])
    mean_diffs, mean_stds = np.mean(diff_hist), np.std(diff_hist)
    ax[0,1].hist(diff_hist,bins=20, range=(-5,5), histtype='bar',ec = 'white', color = 'tab:blue',alpha = 0.5,fill = True, density = True)
    ax[0,1].plot(plotrange, norm.pdf(plotrange, mean_diffs, mean_stds),color = 'darkorange', linestyle = '--', linewidth = 2.5,label = 'normal fit')
    ax[0,1].set_yscale('log')
    ax[0,1].legend(loc = "upper right",prop={'size': 8})
    ax[0,1].set_xlabel(r'$(v_{\rm{los}}^{\rm{pred}} - v_{\rm{los}}^{\rm{meas}})/\sigma$',labelpad=-5)
    
    h4 = ax[1,1].hist2d((data_test['l']).values,test_preds[:,1], bins=40,norm = LogNorm())
    clb2 = plt.colorbar(h4[3],ax = ax[1,1])
    clb2.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    ax[1,1].plot(x1,y1,'k--')
    ax[1,1].set_xlabel(r'$l$',labelpad=-3)
    ax[1,1].set_ylabel('$\sigma$',labelpad=-5)
    

    ax[0,0].hist((data_test['radial_velocity']).values, bins=50, range=(y_low,y_high), histtype='bar', edgecolor = 'white', color= 'tab:blue',alpha = 0.5, fill = True, label = 'test', density = True )
    ax[0,0].hist(test_preds[:,0], bins=100, range=(y_low,y_high), histtype='step',color = 'darkslateblue', linewidth = 1.3, label = 'predicted', density = True)
    ax[0,0].set_xlabel(r'$v_{\rm{los}}$', labelpad =-2)
    if thresh == 0 and spec == "new": ax[0,0].set_title('Test set, 100 bins, no sigma cut, '+str(len(test_preds[:,0]))+' stars',fontsize=14)
    if thresh != 0 and spec == "new": ax[0,0].set_title('Test set, $\sigma \leq$'+str(thresh)+' km/s, '+str(len(test_preds[:,0]))+' stars',fontsize=14)
    if thresh == 0 and spec == "dimtest":ax[0,0].set_title('Test Set, '+str(len(data_test['radial_velocity'].values))+' stars \n Dim stars (photo_g_mean_mag$\geq$13)', fontsize = 11)
    if thresh != 0 and spec == "dimtest":ax[0,0].set_title('Test set, $\sigma \leq$'+str(thresh)+' km/s, '+str(len(test_preds[:,0]))+' stars\n Dim stars (photo_g_mean_mag$\geq$13)',fontsize=14)	
    ax[0,0].legend(loc = "upper right",prop={'size': 10})
    
    hist_test, bins_test, patches_test = ax[2,1].hist((data_test['radial_velocity']).values, bins=50, range=(y_low,y_high), histtype='bar', edgecolor = 'white', color= 'tab:blue', alpha = 0.5, fill = True, label = 'test' , density = True, zorder = 0)
    bin_centers_test = (bins_test[1:]+bins_test[:-1])/2
    vels_sph_pred_test, min_array, max_array,median_array, hb_list, hb_list_r,hb_list_th,hb_list_phi, min_array_r,max_array_r,min_array_th,max_array_th, min_array_phi,max_array_phi, mc_vr_pred_list,cdf_mc_list= monte_carlo(data_test, test_preds, thresh, thresh_string);
    ax[2,1].fill_between(bin_centers_test,min_array, max_array,label = 'MC spread',color = 'orange', zorder = 10, alpha = 0.5)
    #need to calculate MC kde by hand
    vbins = np.linspace(y_low,y_high,51)
    bin_centers = (vbins[1:]+vbins[:-1])/2
    bin_width = vbins[1]-vbins[0]
    normals = np.array([gaussian(bin_centers,test_preds[i,0],test_preds[i,1]) for i in range(len(test_preds[:,0]))])
    sum_normal = np.sum(normals,axis=0)
    sum_normal = sum_normal/np.sum(sum_normal*bin_width)
    
    kde_interp_func = interp1d(bin_centers, sum_normal) #mc by-hand kde
    
    kde = gaussian_kde((data_test['radial_velocity']).values) #truth kde
    #need to randomly resample from the truth for the dumb human tests
    random_from_kde = kde.resample(len(test_preds[:,0]))
    random_from_kde = random_from_kde[0]
    kde_random_samp = gaussian_kde(random_from_kde)
    kl_div_resample = kl_div(kde.evaluate(bin_centers_test),kde_random_samp.evaluate(bin_centers_test), ((np.abs(y_low)+y_high)/50))
    R2_resample = coeff_determination((data_test['radial_velocity']).values, random_from_kde)
    X2_resample = chi_square((data_test['radial_velocity']).values, random_from_kde,np.ones_like(random_from_kde))
    #also need to do test just setting v_los to 0
    filler_array = np.zeros_like(bin_centers_test)
    filler_array[25] = 1
    kl_div_zero = kl_div(kde.evaluate(bin_centers_test),filler_array, ((np.abs(y_low)+y_high)/50))
    R2_zero = coeff_determination((data_test['radial_velocity']).values, np.zeros_like(test_preds[:,0]))
    X2_zero = chi_square((data_test['radial_velocity']).values, np.zeros_like(test_preds[:,0]),np.ones_like(test_preds[:,0]))
    
    with open("klresamp_list.txt", "a") as klresamp_file:
       klresamp_file.write("\n")
       if thresh == 0: klresamp_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_div_resample))
       #else: a_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
    klresamp_file.close()
    with open("r2resamp_list.txt", "a") as r2resamp_file:
       r2resamp_file.write("\n")
       if thresh == 0: r2resamp_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' R2 = '+str(R2_resample))
       #else: a_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
    r2resamp_file.close()
    with open("x2resamp_list.txt", "a") as x2resamp_file:
       x2resamp_file.write("\n")
       if thresh == 0: x2resamp_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' X2 = '+str(X2_resample))
       #else: a_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
    x2resamp_file.close()

    with open("klzero_list.txt", "a") as klzero_file:
       klzero_file.write("\n")
       if thresh == 0: klzero_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_div_zero))
       #else: a_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
    klzero_file.close()
    with open("r2zero_list.txt", "a") as r2zero_file:
       r2zero_file.write("\n")
       if thresh == 0: r2zero_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' R2 = '+str(R2_zero))
       #else: a_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
    r2zero_file.close()
    with open("x2zero_list.txt", "a") as x2zero_file:
       x2zero_file.write("\n")
       if thresh == 0: x2zero_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' X2 = '+str(X2_zero))
       #else: a_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
    x2zero_file.close()

    ax[2,1].plot(bin_centers_test,kde.evaluate(bin_centers_test),zorder = 30, color = 'green', label = 'truth kde' )

    ax[2,1].plot(bin_centers_test, sum_normal,label = 'pred kde',color = 'red')
    
    kl_divergence = kl_div(kde.evaluate(bin_centers_test),sum_normal, ((np.abs(y_low)+y_high)/50))
    
    ax[2,1].hist(test_preds[:,0], bins=50, range=(y_low,y_high), histtype='step',color = 'darkslateblue',linewidth = 1.3, label = 'predicted', density = True, zorder = 20)
    ax[2,1].set_xlabel(r'$v_{\rm{los}}$, KL = '+str('%.5f'%(kl_divergence)))
    ax[2,1].legend(loc = "upper right",prop={'size': 10})
    if not os.path.exists('KL_list.txt'): 
        a_file= open("KL_list.txt", "w")
        a_file.write("\n")
        if thresh == 0: a_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
        else: a_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
    else:
        with open("KL_list.txt", "a") as a_file:
            a_file.write("\n")
            if thresh == 0: a_file.write(txt + ' sigmaleq '+str(np.max(test_preds[:,1]))+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
            else: a_file.write(txt + ' sigmaleq '+str(thresh)+ ', '+str(len(data_test['radial_velocity'].values))+' stars,'+' KL = '+str(kl_divergence))
    a_file.close()
    hb_mean=ax[2,2].hexbin((data_test['radial_velocity']).values, np.zeros_like((data_test['radial_velocity']).values),gridsize=100, norm = LogNorm(),extent=[-200, 200, -200, 200])
    hb_mean.set_array(np.mean(hb_list, axis = 0))
    x1 = np.linspace(-150,150,1000)
    y1 = x1
    ax[2,2].plot(x1,y1,'k--')
    ax[2,2].set_ylabel(r'$v_{\rm{los}}^{\rm{pred, MC}}$',labelpad=-10)
    ax[2,2].set_xlabel(r'$v_{\rm{los}}^{\rm{meas}}$')
    hb_mean.set_clim(1,(np.max(hb_list)/2)*1.5)
    clb6 = plt.colorbar(hb_mean,ax = ax[2,2])
    clb6.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    
    #'vr','vphi','vtheta'
    hb_r = ax[3,0].hexbin((data_test['vr']).values, vels_sph_pred_test[:,0],gridsize=100, norm = LogNorm(),extent=[-250, 250, -250, 250],rasterized=True)
    x1 = np.linspace(-250,250,1000)
    y1 = x1
    ax[3,0].plot(x1,y1,'k--')
    ax[3,0].set_ylabel(r'$v_{\rm{r}}^{\rm{pred}}$',labelpad=-10)
    ax[3,0].set_xlabel(r'$v_{\rm{r}}^{\rm{meas}}$')
    clb7 = plt.colorbar(hb_r, ax = ax[3,0])
    clb7.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    
    hb_t = ax[3,1].hexbin((data_test['vtheta']).values, vels_sph_pred_test[:,1],gridsize=100, norm = LogNorm(),extent=[-250, 250, -250, 250])
    x2 = np.linspace(-250,250,1000)
    y2 = x2
    ax[3,1].plot(x2,y2,'k--')
    ax[3,1].set_ylabel(r'$v_{\rm{\theta}}^{\rm{pred}}$',labelpad=-10)
    ax[3,1].set_xlabel(r'$v_{\rm{\theta}}^{\rm{meas}}$')
    clb8 = plt.colorbar(hb_t,ax = ax[3,1])
    clb8.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    
    hb_p= ax[3,2].hexbin((data_test['vphi']).values, vels_sph_pred_test[:,2],gridsize=100, norm = LogNorm(),extent=[-450, 0, -450, 0])
    x3 = np.linspace(-450,0,1000)
    y3 = x3
    ax[3,2].plot(x3,y3,'k--')
    ax[3,2].set_ylabel(r'$v_{\rm{\phi}}^{\rm{pred}}$',labelpad=-5)
    ax[3,2].set_xlabel(r'$v_{\rm{\phi}}^{\rm{meas}}$')
    clb9 = plt.colorbar(hb_p, ax = ax[3,2])
    clb9.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    
    hist_test_r, bins_test_r, patches_test_r = ax[4,0].hist((data_test['vr']).values, bins=50, range=(y_low,y_high), histtype='bar', edgecolor = 'white', color= 'tab:blue',alpha = 0.5, fill = True,  label = 'test' )
    bin_centers_test_r = (bins_test_r[1:]+bins_test_r[:-1])/2
    ax[4,0].fill_between(bin_centers_test_r,min_array_r, max_array_r,label = 'MC spread',color = 'orange',alpha = 0.5)
    ax[4,0].hist(vels_sph_pred_test[:,0], bins=50, range=(y_low,y_high), histtype='step',color = 'darkslateblue', linewidth = 1.3,label = 'predicted')
    ax[4,0].set_xlabel(r'$v_{\rm{r}}$', labelpad =-2)
    ax[4,0].legend(loc = "upper right",prop={'size': 10})
    
    hist_test_th, bins_test_th, patches_test_th = ax[4,1].hist((data_test['vtheta']).values, bins=50, range=(y_low,y_high), histtype='bar', edgecolor = 'white', color= 'tab:blue',alpha = 0.5,fill = True, label = 'test', zorder = 0)
    bin_centers_test_th = (bins_test_th[1:]+bins_test_th[:-1])/2
    ax[4,1].fill_between(bin_centers_test_th,min_array_th, max_array_th,label = 'MC spread',color = 'orange', alpha = 0.5, zorder = 10)
    ax[4,1].hist(vels_sph_pred_test[:,1], bins=50, range=(y_low,y_high), histtype='step',color = 'darkslateblue',linewidth = 1.3, label = 'predicted', zorder = 20)
    ax[4,1].set_xlabel(r'$v_{\rm{\theta}}$', labelpad =-2)
    ax[4,1].legend(loc = "upper right",prop={'size': 10})
    
    hist_test_phi, bins_test_phi, patches_test_phi = ax[4,2].hist((data_test['vphi']).values, bins=50, range=(-450,0), histtype='bar', edgecolor = 'white', color= 'tab:blue', alpha = 0.5,fill = True,  label = 'test', zorder = 0)
    bin_centers_test_phi = (bins_test_phi[1:]+bins_test_phi[:-1])/2
    ax[4,2].fill_between(bin_centers_test_phi,min_array_phi, max_array_phi,label = 'MC spread',color = 'orange', alpha = 0.5, zorder = 10)
    ax[4,2].hist(vels_sph_pred_test[:,2], bins=50, range=(-450,0), histtype='step',color = 'darkslateblue', linewidth = 1.3,label = 'predicted', zorder = 20)
    ax[4,2].set_xlabel(r'$v_{\rm{\phi}}$', labelpad =-2)
    ax[4,2].legend(loc = "upper right",prop={'size': 10})
    
    hb_mean_r=ax[5,0].hexbin((data_test['vr']).values, np.zeros_like((data_test['vr']).values), gridsize=100, norm = LogNorm(),extent=[-250, 250, -250, 250])
    hb_mean_r.set_array(np.mean(hb_list_r, axis = 0))
    x1 = np.linspace(-250,250,1000)
    y1 = x1
    ax[5,0].plot(x1,y1,'k--')
    ax[5,0].set_ylabel(r'$v_{\rm{r}}^{\rm{pred, MC}}$',labelpad=-10)
    ax[5,0].set_xlabel(r'$v_{\rm{r}}^{\rm{meas}}$')
    hb_mean_r.set_clim(1,(np.max(hb_list_r)/2)*1.5)
    clb10 = plt.colorbar(hb_mean_r,ax = ax[5,0])
    clb10.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    
    hb_mean_th=ax[5,1].hexbin((data_test['vtheta']).values, np.zeros_like((data_test['vtheta']).values), gridsize=100, norm = LogNorm(),extent=[-250, 250, -250, 250])
    hb_mean_th.set_array(np.mean(hb_list_th, axis = 0))
    x1 = np.linspace(-250,250,1000)
    y1 = x1
    ax[5,1].plot(x1,y1,'k--')
    ax[5,1].set_ylabel(r'$v_{\rm{\theta}}^{\rm{pred, MC}}$',labelpad=-10)
    ax[5,1].set_xlabel(r'$v_{\rm{\theta}}^{\rm{meas}}$')
    hb_mean_th.set_clim(1,(np.max(hb_list_th)/2)*1.5)
    clb11 = plt.colorbar(hb_mean_th,ax = ax[5,1])
    clb11.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
    
    hb_mean_phi=ax[5,2].hexbin((data_test['vphi']).values, np.zeros_like((data_test['vphi']).values), gridsize=100, norm = LogNorm(),extent=[-450, 250, -450,250])
    hb_mean_phi.set_array(np.mean(hb_list_phi, axis = 0))
    x1 = np.linspace(-450,250,1000)
    y1 = x1
    ax[5,2].plot(x1,y1,'k--')
    ax[5,2].set_ylabel(r'$v_{\rm{\phi}}^{\rm{pred, MC}}$',labelpad=-10)
    ax[5,2].set_xlabel(r'$v_{\rm{\phi}}^{\rm{meas}}$')
    hb_mean_phi.set_clim(1,(np.max(hb_list_phi)/2)*1.5)
    clb12 = plt.colorbar(hb_mean_phi,ax=ax[5,2])
    clb12.set_label('Density', labelpad=-25, y=1.08, rotation=0,fontsize=10)
   
    txt =('input vars = '+ str(use_cols)+ ', '+neurons+' '+num_samp+' '+act_func+' '+dropout+' '+lweights+' '+spec)
    fig.suptitle(txt)


    fig.savefig(folder_name+'/'+filename+'_withKL_sigmaleq_'+thresh_string+'.png',bbox_inches='tight',rasterized=True)
    np.save(folder_name+'/'+filename+'_testpreds_sigmaleq_'+thresh_string+'.npy',test_preds)
    clb1.remove()
    clb2.remove()
    clb3.remove()
    clb4.remove()
    clb5.remove()
    clb6.remove()
    clb7.remove()
    clb8.remove()
    clb9.remove()
    clb10.remove()
    clb11.remove()
    clb12.remove()
    

# %%
#if not os.path.exists(folder_name+'/'+filename+'_withKL_sigmaleq_0.png'):
rounded_quant= np.insert(rounded_quant,0,0.0)
quant_string = np.insert(quant_string,0, '0')
print(rounded_quant)
print(quant_string)
plot_test(0,'0')

#for elem_i in range(len(rounded_quant)):
#    save_indices(rounded_quant[elem_i],quant_string[elem_i])
#    plot_test(rounded_quant[elem_i],quant_string[elem_i])

# %%
#CombinedModel.save(folder_name+'/network.h5')
