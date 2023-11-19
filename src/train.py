from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from src.models.crnn import CRNN
from src.utils.logger import Logger
from src.utils.losses import CTCLoss
from src.utils.metrics import BatchMeter
from src.utils.torch_utils import DataUtils
from src.data.transformation import TransformCRNN
from src.data.dataset_ic15 import Icdar15Dataset, icdar15_collate_fn

from . import config as cfg

import os
import argparse

logger = Logger.get_logger("__TRAINING__")


class Trainer(object):
    def __init__(self, args) -> None:
        self.args = args
        self.start_epoch = 1
        self.best_acc = 0.0
        self.create_data_loader()
        self.create_model()
    
    def create_data_loader(self):
        self.train_dataset = Icdar15Dataset(mode='Train')
        self.valid_dataset = Icdar15Dataset(mode='Eval')
        self.train_loader = DataLoader(self.train_dataset, 
                                       batch_size=self.args.batch_size, 
                                       shuffle=self.args.shuffle,
                                       num_workers=self.args.num_workers,
                                       pin_memory=self.args.pin_memory,
                                       collate_fn=icdar15_collate_fn)
    
    def create_model(self):
        self.model = CRNN().to(self.args.device)
        self.loss_func = CTCLoss()
        self.optimizer = torch.optim.AdamW(self.model.parameters(), lr=self.args.lr, amsgrad=True)
    

    def train(self):
        for epoch in range(self.start_epoch, self.args.epochs):
            mt_loss = BatchMeter()
            for i, (images, labels, labels_len) in enumerate(self.train_loader):
                self.model.train()
                bz = images.size(0)
                images = DataUtils.to_device(images)
                labels = DataUtils.to_device(labels)
                out = self.model(images)
                out_log_probs = F.log_softmax(out, dim=2)
                labels_len = torch.flatten(labels_len)
                images_len = torch.tensor([out.size(0)] * bz, dtype=torch.long)

                loss = self.loss_func(out_log_probs, labels, images_len, labels_len)
                
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()

                mt_loss.update(loss.item())
                print(f"Epoch {epoch} - batch {i+1}/{len(self.train_dataset)} - loss: {mt_loss.get_value()}", end='\r')
            logger.info(f"Epoch {epoch} - loss: {mt_loss.get_value('mean')}")
    

    def save_ckpt(self, save_path, best_acc, epoch):
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        ckpt_dict = {
            "model": self.model.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "best_acc": best_acc,
            "epoch": epoch
        }
        logger.info(f"Saving checkpoint to {save_path}")
        torch.save(ckpt_dict, save_path)

    def resume_training(self, ckpt):
        self.best_acc = ckpt['best_acc']
        start_epoch = ckpt['epoch'] + 1
        self.optimizer.load_state_dict(ckpt['optimizer'])
        self.model.load_state_dict(ckpt['mode'])

        return start_epoch
    

def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", default=cfg['Train']['loader']['epochs'])
    parser.add_argument("--batch_size", default=cfg['Train']['loader']['batch_size'])
    parser.add_argument("--shuffle", default=cfg['Train']['loader']['shuffle'])
    parser.add_argument("--num_workers", default=cfg['Train']['loader']['num_workers'])
    parser.add_argument("--pin_memory", default=cfg['Train']['loader']['use_shared_memory'])
    parser.add_argument("--device", default=cfg['Global']['device'])
    parser.add_argument("--lr", default=cfg['Optimizer']['lr'])
    
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    args = cli()
    trainer = Trainer(args)
    trainer.train()
