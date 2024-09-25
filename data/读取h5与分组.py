import h5py
import os
import numpy as np
import nrrd
import SimpleITK as sitk
import random

file_data='H:\img_sgementation\my_segmentation\data\image_cut'
pathname=[]
train=[]
val=[]
test=[]
for root, dirs, files in os.walk(file_data):
    # print(files)
    for file in files:
        path = os.path.join(root, file)
        pathname.append(path)
print(pathname[0].split('\\')[5])
random_elements = random.sample(pathname, int(len(pathname)*0.2))
# print(type(random_elements))
for n in pathname:
    if n not in random_elements:
        train.append(n)
val=random.sample(random_elements, int(len(random_elements)*0.5))

for n in random_elements:
    if n not in val:
        test.append(n)

f=open(r'H:\img_sgementation\my_segmentation\data\train.txt','w')
f2=open(r'H:\img_sgementation\my_segmentation\data\val.txt','w')
f3=open(r'H:\img_sgementation\my_segmentation\data\test.txt','w')
for n in train:
    f.write(n.split('\\')[5]+'\n')
for n in val:
    f2.write(n.split('\\')[5]+'\n')
for n in test:
    f3.write(n.split('\\')[5]+'\n')