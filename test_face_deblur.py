from __future__ import print_function
import argparse
import os
import sys
import random
import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
cudnn.benchmark = True
cudnn.fastest = True
import torch.optim as optim
import torchvision.utils as vutils
from torch.autograd import Variable

from misc import *
import models.face_fed as net

from myutils.vgg16 import Vgg16
from myutils import utils
import pdb

# Pre-defined Parameters
parser = argparse.ArgumentParser()
parser.add_argument('--dataset', required=False,
  default='pix2pix',  help='')
parser.add_argument('--dataroot', required=False,
  default='./facades/github/', help='path to trn dataset')
parser.add_argument('--valDataroot', required=False,
  default='/home/dejavu/Code/UMSN-Face-Deblurring/output_images', help='path to val dataset')
parser.add_argument('--mode', type=str, default='B2A', help='B2A: facade, A2B: edges2shoes')
parser.add_argument('--batchSize', type=int, default=1, help='input batch size')
parser.add_argument('--valBatchSize', type=int, default=1, help='input batch size')
parser.add_argument('--originalSize', type=int,
  default=128, help='the height / width of the original input image')
parser.add_argument('--imageSize', type=int,
  default=128, help='the height / width of the cropped input image to network')
parser.add_argument('--inputChannelSize', type=int,
  default=3, help='size of the input channels')
parser.add_argument('--outputChannelSize', type=int,
  default=3, help='size of the output channels')
parser.add_argument('--ngf', type=int, default=64)
parser.add_argument('--ndf', type=int, default=64)
parser.add_argument('--niter', type=int, default=400, help='number of epochs to train for')
parser.add_argument('--lrD', type=float, default=0.0002, help='learning rate, default=0.0002')
parser.add_argument('--lrG', type=float, default=0.0002, help='learning rate, default=0.0002')
parser.add_argument('--annealStart', type=int, default=0, help='annealing learning rate start to')
parser.add_argument('--annealEvery', type=int, default=400, help='epoch to reaching at learning rate of 0')
parser.add_argument('--lambdaGAN', type=float, default=0.01, help='lambdaGAN')
parser.add_argument('--lambdaIMG', type=float, default=1, help='lambdaIMG')
parser.add_argument('--poolSize', type=int, default=50, help='Buffer size for storing previously generated samples from G')
parser.add_argument('--wd', type=float, default=0.0000, help='weight decay in D')
parser.add_argument('--beta1', type=float, default=0.5, help='beta1 for adam')
parser.add_argument('--netG', default='./pretrained_models/Deblur_epoch_Best.pth', help="path to netG (to continue training)")
parser.add_argument('--netD', default='', help="path to netD (to continue training)")
parser.add_argument('--workers', type=int, help='number of data loading workers', default=1)
parser.add_argument('--exp', default='sample', help='folder to output images and model checkpoints')
parser.add_argument('--display', type=int, default=5, help='interval for displaying train-logs')
parser.add_argument('--evalIter', type=int, default=500, help='interval for evauating(generating) images from valDataroot')
opt = parser.parse_args()#pt.originalSize
print(opt)



create_exp_dir(opt.exp)
opt.manualSeed = random.randint(1, 10000)
random.seed(opt.manualSeed)
torch.manual_seed(opt.manualSeed)
torch.cuda.manual_seed_all(opt.manualSeed)
print("Random Seed: ", opt.manualSeed)

# Initialize dataloader
# dataloader = getLoader(opt.dataset,
#                        opt.dataroot,
#                        opt.originalSize,
#                        opt.imageSize,
#                        opt.batchSize,
#                        opt.workers,
#                        mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5),
#                        split='val',
#                        shuffle=True,
#                        seed=opt.manualSeed)
opt.dataset='pix2pix_val'

valDataloader = getLoader(opt.dataset,
                          opt.valDataroot,
                          opt.originalSize, #opt.originalSize,
                          opt.imageSize,
                          opt.valBatchSize,
                          opt.workers,
                          mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5),
                          split='val',
                          shuffle=False,
                          seed=opt.manualSeed)

# get logger
# trainLogger = open('%s/train.log' % opt.exp, 'w')



ngf = opt.ngf
ndf = opt.ndf
inputChannelSize = opt.inputChannelSize
outputChannelSize= opt.outputChannelSize


# Load Pre-trained derain model
netS=net.Segmentation()
netG=net.Deblur_segdl()

#netC.apply(weights_init)


netG.apply(weights_init)
if opt.netG != '':
    state_dict_g = torch.load(opt.netG)
    new_state_dict_g = {}
    for k, v in state_dict_g.items():
        name = k[7:] # remove `module.`
        #print(k)
        new_state_dict_g[name] = v
    # load params
    netG.load_state_dict(new_state_dict_g)
  #netG.load_state_dict(torch.load(opt.netG))
print(netG)
netG.eval()
#netS.apply(weights_init)
netS.load_state_dict(torch.load('./pretrained_models/SMaps_Best.pth'))
#netS.eval()
netS.cuda()
netG.cuda()

# Initialize testing data
target= torch.FloatTensor(opt.batchSize, outputChannelSize, opt.imageSize, opt.imageSize)
input = torch.FloatTensor(opt.batchSize, inputChannelSize, opt.imageSize, opt.imageSize)

val_target= torch.FloatTensor(opt.valBatchSize, outputChannelSize, opt.imageSize, opt.imageSize)
val_input = torch.FloatTensor(opt.valBatchSize, inputChannelSize, opt.imageSize, opt.imageSize)
label_d = torch.FloatTensor(opt.batchSize)


target = torch.FloatTensor(opt.batchSize, outputChannelSize, opt.imageSize, opt.imageSize)
input = torch.FloatTensor(opt.batchSize, inputChannelSize, opt.imageSize, opt.imageSize)
depth = torch.FloatTensor(opt.batchSize, inputChannelSize, opt.imageSize, opt.imageSize)
ato = torch.FloatTensor(opt.batchSize, inputChannelSize, opt.imageSize, opt.imageSize)


val_target = torch.FloatTensor(opt.valBatchSize, outputChannelSize, opt.imageSize, opt.imageSize)
val_input = torch.FloatTensor(opt.valBatchSize, inputChannelSize, opt.imageSize, opt.imageSize)
val_depth = torch.FloatTensor(opt.valBatchSize, inputChannelSize, opt.imageSize, opt.imageSize)
val_ato = torch.FloatTensor(opt.valBatchSize, inputChannelSize, opt.imageSize, opt.imageSize)


target_128= torch.FloatTensor(opt.batchSize, outputChannelSize, (opt.imageSize//4), (opt.imageSize//4))
input_128 = torch.FloatTensor(opt.batchSize, inputChannelSize, (opt.imageSize//4), (opt.imageSize//4))
target_256= torch.FloatTensor(opt.batchSize, outputChannelSize, (opt.imageSize//2), (opt.imageSize//2))
input_256 = torch.FloatTensor(opt.batchSize, inputChannelSize, (opt.imageSize//2), (opt.imageSize//2))

val_target_128= torch.FloatTensor(opt.batchSize, outputChannelSize, (opt.imageSize//4), (opt.imageSize//4))
val_input_128 = torch.FloatTensor(opt.batchSize, inputChannelSize, (opt.imageSize//4), (opt.imageSize//4))
val_target_256= torch.FloatTensor(opt.batchSize, outputChannelSize, (opt.imageSize//2), (opt.imageSize//2))
val_input_256 = torch.FloatTensor(opt.batchSize, inputChannelSize, (opt.imageSize//2), (opt.imageSize//2))

target, input, depth, ato = target.cuda(), input.cuda(), depth.cuda(), ato.cuda()
val_target, val_input, val_depth, val_ato = val_target.cuda(), val_input.cuda(), val_depth.cuda(), val_ato.cuda()

target = Variable(target, volatile=True)
input = Variable(input,volatile=True)
depth = Variable(depth,volatile=True)
ato = Variable(ato,volatile=True)

target_128, input_128 = target_128.cuda(), input_128.cuda()
val_target_128, val_input_128 = val_target_128.cuda(), val_input_128.cuda()
target_256, input_256 = target_256.cuda(), input_256.cuda()
val_target_256, val_input_256 = val_target_256.cuda(), val_input_256.cuda()

target_128 = Variable(target_128)
input_128 = Variable(input_128)
target_256 = Variable(target_256)
input_256 = Variable(input_256)

label_d = Variable(label_d.cuda())

def norm_ip(img, min, max):
    img.clamp_(min=min, max=max)
    img.add_(-min).div_(max - min)

    return img


def norm_range(t, range):
    if range is not None:
        norm_ip(t, range[0], range[1])
    else:
        norm_ip(t, -1, +1)
        
    return t#norm_ip(t, t.min(), t.max())

# get optimizer
optimizerG = optim.Adam(netG.parameters(), lr = opt.lrG, betas = (opt.beta1, 0.999), weight_decay=0.00005)


# Begin Testing
for epoch in range(1):
  heavy, medium, light=200, 200, 200
  for i, data in enumerate(valDataloader, 0):
    if 1:
      print('Image:'+str(i))
      import time
      data_val = data
      
      t0 = time.time()

      val_input_cpu, val_target_cpu = data_val

      val_target_cpu, val_input_cpu = val_target_cpu.float().cuda(), val_input_cpu.float().cuda()
      val_batch_output = torch.FloatTensor(val_input.size()).fill_(0)

      val_input.resize_as_(val_input_cpu).copy_(val_input_cpu)
      val_target=Variable(val_target_cpu, volatile=True)


      z=0

      with torch.no_grad():
        for idx in range(val_input.size(0)):
            single_img = val_input[idx,:,:,:].unsqueeze(0)
            val_inputv = Variable(single_img, volatile=True)
            print (val_inputv.size())
            # val_inputv = val_inputv.float().cuda()
            val_inputv_256 = torch.nn.functional.interpolate(val_inputv,scale_factor=0.5)
            val_inputv_128 = torch.nn.functional.interpolate(val_inputv,scale_factor=0.25)
            
            ## Get de-rained results ##
            #residual_val, x_hat_val, x_hatlv128, x_hatvl256 = netG(val_inputv, val_inputv_256, val_inputv_128)

            t1 = time.time()
            print('running time:'+str(t1 - t0))
            from PIL import Image

            #x_hat_val = netG(val_inputv)
            #smaps_vl = netS(val_inputv)
            #S_valinput = torch.cat([smaps_vl,val_inputv],1)
            """smaps,smaps64 = netS(val_inputv,val_inputv_256)
            S_input = torch.cat([smaps,val_inputv],1)
            x_hat_val, x_hat_val64 = netG(val_inputv,val_inputv_256,smaps,smaps64)"""
            
            # val_inputv_256 对应1，3，64，64
            #x_hatcls1,x_hatcls2,x_hatcls3,x_hatcls4,x_lst1,x_lst2,x_lst3,x_lst4 = netG(val_inputv,val_inputv_256,smaps_i,smaps_i64,class1,class2,class3,class4)
            smaps,smaps64 = netS(val_inputv,val_inputv_256)
            # smaps: 1,4,128,128 smaps64 1,4,64,64
            # class1 1,1,128,128
            class1 = torch.zeros([1,1,opt.originalSize,opt.originalSize], dtype=torch.float32)
            class1[:,0,:,:] = smaps[:,0,:,:]
            class2 = torch.zeros([1,1,opt.originalSize,opt.originalSize], dtype=torch.float32)
            class2[:,0,:,:] = smaps[:,1,:,:]
            class3 = torch.zeros([1,1,opt.originalSize,opt.originalSize], dtype=torch.float32)
            class3[:,0,:,:] = smaps[:,2,:,:]
            class4 = torch.zeros([1,1,opt.originalSize,opt.originalSize], dtype=torch.float32)
            class4[:,0,:,:] = smaps[:,3,:,:]
            class_msk1 = torch.zeros([1,3,opt.originalSize,opt.originalSize], dtype=torch.float32)
            class_msk1[:,0,:,:] = smaps[:,0,:,:] 
            class_msk1[:,1,:,:] = smaps[:,0,:,:] 
            class_msk1[:,2,:,:] = smaps[:,0,:,:] 
            class_msk2 = torch.zeros([1,3,opt.originalSize,opt.originalSize], dtype=torch.float32)
            class_msk2[:,0,:,:] = smaps[:,1,:,:]
            class_msk2[:,1,:,:] = smaps[:,1,:,:]
            class_msk2[:,2,:,:] = smaps[:,1,:,:]
            class_msk3 = torch.zeros([1,3,opt.originalSize,opt.originalSize], dtype=torch.float32)
            class_msk3[:,0,:,:] = smaps[:,2,:,:] 
            class_msk3[:,1,:,:] = smaps[:,2,:,:] 
            class_msk3[:,2,:,:] = smaps[:,2,:,:] 
            class_msk4 = torch.zeros([1,3,opt.originalSize,opt.originalSize], dtype=torch.float32)
            class_msk4[:,0,:,:] = smaps[:,3,:,:]  
            class_msk4[:,1,:,:] = smaps[:,3,:,:]
            class_msk4[:,2,:,:] = smaps[:,3,:,:]
            class1 = class1.float().cuda()
            class2 = class2.float().cuda()
            class3 = class3.float().cuda()
            class4 = class4.float().cuda()
            class_msk4 = class_msk4.float().cuda()
            class_msk3 = class_msk3.float().cuda()
            class_msk2 = class_msk2.float().cuda()
            class_msk1 = class_msk1.float().cuda()
            x_hat_val, x_hat_val64,xmask1,xmask2,xmask3,xmask4,xcl_class1,xcl_class2,xcl_class3,xcl_class4 = netG(val_inputv,val_inputv_256,smaps,class1,class2,class3,class4,val_inputv,class_msk1,class_msk2,class_msk3,class_msk4)
            # x_hat1,x_hat64,xmask1,xmask2,xmask3,xmask4,xcl_class1,xcl_class2,xcl_class3,xcl_class4 = netG(input,input_256,smaps_i,class1,class2,class3,class4,target,class_msk1,class_msk2,class_msk3,class_msk4)
            #x_hat_val.data
            #val_batch_output[idx,:,:,:].copy_(x_hat_val.data[0,1,:,:])
            # print(torch.mean(xmask1),torch.mean(xmask2),torch.mean(xmask3),torch.mean(xmask4))
            print (smaps.size())
            tensor = x_hat_val.data.cpu()


            ###   Save the de-rained results #####
            from PIL import Image
            directory = './result_all/deblurh/'#'./result_all/new_model_data/DID-MDN/'
            if not os.path.exists(directory):
                os.makedirs(directory)

            tensor = torch.squeeze(tensor)
            tensor=norm_range(tensor, None)
            print(tensor.min(),tensor.max())

            filename='./result_all/deblurh_mmpd/'+str(i+1)+'.png'
            ndarr = tensor.mul(255).clamp(0, 255).byte().permute(1, 2, 0).numpy()
            im = Image.fromarray(ndarr)

            im.save(filename)
      
