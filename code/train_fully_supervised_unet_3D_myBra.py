import argparse
import logging
import os
import random

import numpy as np
import torch
import torch.backends.cudnn as cudnn
import torch.optim as optim
from tensorboardX import SummaryWriter
from torch.nn.modules.loss import CrossEntropyLoss
from torch.utils.data import DataLoader
from torchvision import transforms
from tqdm import tqdm

# from dataloaders import utils
from dataloaders.my_brain import (myBraTS, RandomCrop,
                                   RandomRotFlip, ToTensor)
from networks.net_factory_3d import net_factory_3d
from utils import losses
from val_3D import test_all_case_base

parser = argparse.ArgumentParser()
parser.add_argument('--root_path', type=str,
                    default='../data', help='Name of Experiment')
parser.add_argument('--exp', type=str,
                    default='myBra/UNet3D-FullyS', help='experiment_name')
parser.add_argument('--model', type=str,
                    default='unet_3D', help='model_name')
parser.add_argument('--max_iterations', type=int,
                    default=30000, help='maximum epoch number to train')
parser.add_argument('--batch_size', type=int, default=4,
                    help='batch_size per gpu')
parser.add_argument('--deterministic', type=int,  default=1,
                    help='whether use deterministic training')
parser.add_argument('--base_lr', type=float,  default=0.01,
                    help='segmentation network learning rate')
parser.add_argument('--patch_size', type=list,  default=[30, 512, 512],
                    help='patch size of network input')
parser.add_argument('--seed', type=int,  default=1337, help='random seed')
parser.add_argument('--labeled_num', type=int, default=50,
                    help='labeled data')
parser.add_argument('--num_tries', type=str,  default='1',
                    help='number of experiments tryings')

args = parser.parse_args()


def train(args, snapshot_path):
    base_lr = args.base_lr
    train_data_path = args.root_path
    batch_size = args.batch_size
    max_iterations = args.max_iterations
    num_classes = 2
    model = net_factory_3d(net_type=args.model, in_chns=1, class_num=num_classes)
    db_train = myBraTS(base_dir=train_data_path,
                         split='train',
                         num=args.labeled_num,
                         transform=transforms.Compose([
                            #  RandomRotFlip(),
                            #  RandomCrop(args.patch_size),
                            #  CenterCrop(30,300,300)
                             ToTensor(),
                         ]))

    def worker_init_fn(worker_id):
        random.seed(args.seed + worker_id)

    trainloader = DataLoader(db_train, batch_size=batch_size, shuffle=True,
                             num_workers=0, pin_memory=True, worker_init_fn=worker_init_fn)
    if os._exists(r'H:\img_sgementation\ICL-main\experiments\BraTS19\UNet3D-FullyS_25_labeled\unet_3D_exp_1\model\model_best.pth'):
        model.load_state_dict(torch.load(r'H:\img_sgementation\ICL-main\experiments\BraTS19\UNet3D-FullyS_25_labeled\unet_3D_exp_1\model\model_best.pth'))
    model.train()

    optimizer = optim.SGD(model.parameters(), lr=base_lr,
                          momentum=0.9, weight_decay=0.0001)
    ce_loss = CrossEntropyLoss()
    dice_loss = losses.DiceLoss(num_classes)

    writer = SummaryWriter(snapshot_path + '/log')
    logging.info("{} iterations per epoch".format(len(trainloader)))

    iter_num = 0
    max_epoch = max_iterations // len(trainloader) + 1
    best_performance = 0.0
    iterator = tqdm(range(max_epoch), ncols=70)
    for epoch_num in iterator:
        for i_batch, sampled_batch in enumerate(trainloader):

            volume_batch, label_batch = sampled_batch['image'], sampled_batch['label']
            volume_batch, label_batch = volume_batch.cuda(), label_batch.cuda()

            outputs = model(volume_batch)
            outputs_soft = torch.softmax(outputs, dim=1)

            loss_ce = ce_loss(outputs, label_batch)
            loss_dice = dice_loss(outputs_soft, label_batch.unsqueeze(1))
            loss = 0.5 * (loss_dice + loss_ce)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            lr_ = base_lr * (1.0 - iter_num / max_iterations) ** 0.9
            for param_group in optimizer.param_groups:
                param_group['lr'] = lr_

            iter_num = iter_num + 1
            writer.add_scalar('Info/lr', lr_, iter_num)
            writer.add_scalar('Loss/loss', loss, iter_num)
            writer.add_scalar('Loss/loss_ce', loss_ce, iter_num)
            writer.add_scalar('Loss/loss_dice', loss_dice, iter_num)

            logging.info(
                'iteration %d : loss : %f, loss_ce: %f, loss_dice: %f' %
                (iter_num, loss.item(), loss_ce.item(), loss_dice.item()))

            # if iter_num % 20 == 0:
            #     image = volume_batch[0, 0:1, :, :, 20:61:10].permute(
            #         3, 0, 1, 2).repeat(1, 3, 1, 1)
            #     grid_image = make_grid(image, 5, normalize=True)
            #     writer.add_image('train/Image', grid_image, iter_num)

            #     image = outputs_soft[0, 1:2, :, :, 20:61:10].permute(
            #         3, 0, 1, 2).repeat(1, 3, 1, 1)
            #     grid_image = make_grid(image, 5, normalize=False)
            #     writer.add_image('train/Predicted_label',
            #                      grid_image, iter_num)

            #     image = label_batch[0, :, :, 20:61:10].unsqueeze(
            #         0).permute(3, 0, 1, 2).repeat(1, 3, 1, 1)
            #     grid_image = make_grid(image, 5, normalize=False)
            #     writer.add_image('train/Groundtruth_label',
            #                      grid_image, iter_num)

            if iter_num > 0 and iter_num % 200 == 0:
                model.eval()
                metric_cal = test_all_case_base(model, args.model, args.root_path, test_list="val_test.txt", num_classes=2, patch_size=args.patch_size, stride_xy=64, stride_z=64)
                
                # mean and std for all and each class
                mean_cal, std_cal = 0.0, 0.0
                class_mean, class_std = [], []
                for class_i in range(num_classes-1):
                    _mean = np.mean(metric_cal[class_i], axis=0)
                    _std = np.std(metric_cal[class_i], axis=0)
                    mean_cal += _mean
                    std_cal += _std
                    class_mean.append(_mean)
                    class_std.append(_std)

                mean_dsc, std_dsc = mean_cal[0]/(num_classes-1), std_cal[0]/(num_classes-1)
                mean_hd95, std_hd95 = mean_cal[1]/(num_classes-1), std_cal[1]/(num_classes-1)
                

                # saving the best model
                if mean_dsc > best_performance:
                    best_performance = mean_dsc
                    save_best = os.path.join(snapshot_path+'/model','model_best.pth')
                    torch.save(model.state_dict(), save_best)
                    logging.info('saving best model at iter {}'.format(iter_num))

                # saving and logging metric values 
                writer.add_scalar('metric_all/mean_dice', mean_dsc, iter_num)
                writer.add_scalar('metric_all/mean_hd95', mean_hd95, iter_num)
                writer.add_scalar('metric_all/std_dice', std_dsc, iter_num)
                writer.add_scalar('metric_all/std_hd95', std_hd95, iter_num)

                logging.info('iteration %d : mean_dice : %f  mean_hd95 : %f' % (iter_num, mean_dsc, mean_hd95))
                logging.info('iteration %d : std_dice : %f  std_hd95 : %f' % (iter_num, std_dsc, std_hd95))

                model.train()


            # if iter_num % 3000 == 0:
            #     save_mode_path = os.path.join(
            #         snapshot_path, 'iter_' + str(iter_num) + '.pth')
            #     torch.save(model.state_dict(), save_mode_path)
            #     logging.info("save model to {}".format(save_mode_path))

            if iter_num >= max_iterations:
                break
        if iter_num >= max_iterations:
            iterator.close()
            break
    writer.close()
    return "Training Finished!"


if __name__ == "__main__":
    if not args.deterministic:
        cudnn.benchmark = True
        cudnn.deterministic = False
    else:
        cudnn.benchmark = False
        cudnn.deterministic = True

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed(args.seed)

    snapshot_path = "../experiments/{}_{}_labeled/{}_exp_{}".format(
        args.exp, args.labeled_num, args.model, args.num_tries)
    if not os.path.exists(snapshot_path+'/model'):
        os.makedirs(snapshot_path+'/model')

    logging.basicConfig(filename=snapshot_path+"/log.txt", level=logging.INFO,
                        format='[%(asctime)s.%(msecs)03d] %(message)s', datefmt='%H:%M:%S')
    #logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    logging.info(str(args))
    train(args, snapshot_path)
    