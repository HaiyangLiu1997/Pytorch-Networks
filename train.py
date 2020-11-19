#!usr/bin/env python3
#-*- coding=utf-8 -*-
#python=3.8 pytorch=1.5.0


import os
import random
import cv2
import numpy as np
import torch
import torch.nn.functional as F
from tensorboardX import SummaryWriter
from easydict import EasyDict as edict
from random import randint
import torchvision
import torchvision.transforms as transforms

import time

from network_factory import get_network
from opt_factory import get_opt
from loss_factory import get_loss_func
from loader_factory import get_loader
from test import val
from utils import CalculateAcc,SelfData,load_cfg,model_complexity,plot_result_data,\
    load_checkpoints,print_to_screen,save_checkpoints


def fix_random_seed(cfg):
    random.seed(cfg.DETERMINISTIC.SEED)
    torch.manual_seed(cfg.DETERMINISTIC.SEED)
    torch.cuda.manual_seed(cfg.DETERMINISTIC.SEED)
    torch.backends.cudnn.deterministic = cfg.DETERMINISTIC.CUDNN
    np.random.seed(cfg.DETERMINISTIC.SEED)


def trainer(cfg):
    logger = load_cfg(cfg) 
    fix_random_seed(cfg)    
    
    train_loader = get_loader(cfg.DATASET_TRPE, cfg.PATH.DATA, 'train', cfg=cfg, logger=logger)
    #val_loader = get_loader(cfg.DATASET_TRPE, cfg.PATH.EVAL, 'eval',label_path=cfg.PATH.LABEL, cfg=cfg.TRAIN, logger=logger)
    its_num = len(train_loader)

    model = get_network(cfg.MODEL.NAME, cfg=cfg.MODEL, logger=logger)
    model = torch.nn.DataParallel(model, cfg.GPUS).cuda() if torch.cuda.is_available() else model
    model_complexity(model,cfg,logger)

    cfg.TRAIN.LR_REDUCE = [int(its_num*x) for x in cfg.TRAIN.LR_REDUCE]
    opt_t,lr_scheduler_t = get_opt(model, cfg.TRAIN, logger, 
        its_total=its_num)
    if cfg.TRAIN.WARMUP != 0:
        warm_opt, warm_scheduler = get_opt(model, cfg.TRAIN, logger, 
            is_warm=True, its_total=cfg.TRAIN.WARMUP)
    loss_func = get_loss_func(cfg.MODEL.LOSS, logger=logger)

    current_epoch = load_checkpoints(model, opt_t, cfg.PATH , logger, lr_scheduler_t)
    log_writter = SummaryWriter(cfg.PATH.EXPS+cfg.PATH.NAME)
    
    loss_total = []
   
    for epoch in range(current_epoch, cfg.TRAIN.EPOCHS):
        start_time = time.time()
        #acc_train_class = CalculateAcc()
        loss_train_calss = SelfData()
        model.train()
        data_begin = time.time()

        for its, data in enumerate(train_loader):
            if its < cfg.TRAIN.WARMUP:
                opt = warm_opt
                lr_scheduler = warm_scheduler
            else:
                opt = opt_t
                lr_scheduler = lr_scheduler_t

            data_time = time.time()-data_begin
           
            inputs = data["image"].cuda() if torch.cuda.is_available() else data["image"]
            target_availabilities = data["target_availabilities"].cuda() if torch.cuda.is_available() else data["target_availabilities"]
            targets = data["target_positions"].cuda() if torch.cuda.is_available() else data["target_positions"]
            # Forward pass
            preds, confidences = model(inputs)
            loss = loss_func(targets, preds, confidences, target_availabilities)

            opt.zero_grad()
            loss.backward()
            opt.step()
            lr_scheduler.step()
            
            loss_train_calss.add_value(loss.cpu())
            train_time = time.time()-(data_time+data_begin)
            data_begin = time.time()
            lr = opt.param_groups[0]['lr']
            mem = torch.cuda.memory_cached() / 1E9 if torch.cuda.is_available() else 0
            #acc_train_class.add_value(outputs.cpu(), targets.cpu())
            if its % cfg.PRINT_FRE == 0:
                print_to_screen(loss, lr, its, epoch, its_num, logger, 
                    data_time,train_time,mem)
            if its % cfg.SAVE_FRE == 0:
                save_checkpoints(str(cfg.PATH.EXPS+cfg.PATH.NAME+cfg.PATH.MODEL+f'{its}'), model, opt, epoch,lr_scheduler)
            
            

        end_time = time.time()-start_time
            #logger.info('Train Loss@abg:%.4f\t'%(loss_train_calss.avg()+'Iteration Time:%.2fmin'%(end_time/60))

        
        #acc_val, loss_val = val(val_loader, model, logger, loss_func, epoch, print_fre=cfg.PRINT_FRE,)
        # log_writter.add_scalars("acc",{'acc_train':acc_train_class.print_(),
        #                              'acc_val':acc_val,},
        #                              epoch)
        # acc_total.append(acc_train_class.print_())
        # acc_val_total.append(acc_val)
        loss_total.append(loss_train_calss.avg())
        #losss_val_total.append(loss_val)
        # if best_val[0] < acc_val:
        #     best_val[0] = acc_val
        #     best_val[1] = epoch
        #     save_checkpoints(cfg.PATH.EXPS+cfg.PATH.NAME+cfg.PATH.BESTMODEL, model, opt, epoch,lr_scheduler)
        # logger.info('BestV Prec@1:%.4f\t'%(best_val[0])+"Best Epoch:%d"%(best_val[1]))

    # plot_result_data(acc_total,acc_val_total,loss_total,
    #     losss_val_total,cfg.PATH.EXPS+cfg.PATH.NAME, cfg.TRAIN.EPOCHS)
    log_writter.close()


if __name__ == "__main__":
    from config_lyft import cfg
    trainer(cfg)         