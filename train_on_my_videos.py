import argparse
import numpy as np
import os
from keras.backend import tensorflow_backend as K
from keras.callbacks import ModelCheckpoint, ReduceLROnPlateau
from keras.models import load_model
from keras.optimizers import Adam

from dataloader.keras_data import MyVideos
from keras_models import VGG19_GRU

parser = argparse.ArgumentParser(
    description='Training the spatial motion temporal network')
parser.add_argument(
    '--filepath',
    default='checkpoint/my_videos.hdf5',
    type=str,
    metavar='PATH',
    help="path to checkpoint best model's state and weights")
parser.add_argument(
    '--pretrained',
    default='checkpoint/penn_action.hdf5',
    type=str,
    metavar='PATH',
    help="path to pretrained model weights")
parser.add_argument(
    '--epochs',
    default=20,
    type=int,
    metavar='N',
    help='number of total epochs')
parser.add_argument(
    '--batch-size',
    default=4,
    type=int,
    metavar='N',
    help='number of videos in a single mini-batch')
parser.add_argument(
    '--num-frames-sampled',
    default=16,
    type=int,
    metavar='N',
    help='number of frames sampled from a single video')
parser.add_argument(
    '--train-lr',
    default=1e-3,
    type=float,
    metavar='LR',
    help='learning rate of train stage')
parser.add_argument(
    '--num-workers',
    default=12,
    type=int,
    metavar='N',
    help='number of data loading workers')


def train():
    global args
    args = parser.parse_args()
    print(args)

    train_videos = MyVideos(frames_path='data/MyVideos/train/frames/',
                            poses_path='data/MyVideos/train/poses',
                            batch_size=args.batch_size,
                            num_frames_sampled=args.num_frames_sampled)
    valid_videos = MyVideos(frames_path='data/MyVideos/validation/frames',
                            poses_path='data/MyVideos/validation/poses',
                            batch_size=args.batch_size,
                            num_frames_sampled=args.num_frames_sampled,
                            shuffle=False)

    reduce_lr = ReduceLROnPlateau(monitor='val_acc', factor=np.sqrt(0.1), min_lr=1e-6,
                                  patience=5, verbose=1)
    save_best = ModelCheckpoint(args.filepath,
                                monitor='val_acc',
                                verbose=1,
                                save_best_only=True,
                                mode='max')
    callbacks = [save_best, reduce_lr]

    if os.path.exists(args.filepath):
        model = load_model(args.filepath)
    else: 
        pretrained_model = load_model(args.pretrained)
        model = VGG19_GRU(frames_input_shape=(args.num_frames_sampled,
                                              224,
                                              224,
                                              3),
                          poses_input_shape=(args.num_frames_sampled, 26),
                          classes=len(train_videos.labels))
        for i, layer in enumerate(model.layers[:-3]):
            layer.set_weights(pretrained_model.layers[i].get_weights())
        model.compile(optimizer=Adam(lr=args.train_lr, decay=1e-6),
                      loss='categorical_crossentropy',
                      metrics=['acc'])
        # hacky trick to avoid exhausting GPU's memory
        model.save(args.filepath)
        K.clear_session()
        model = load_model(args.filepath)

    print('Train the GRU component only')
    model.fit_generator(generator=train_videos,
                        epochs=args.epochs,
                        callbacks=callbacks,
                        workers=args.num_workers,
                        validation_data=valid_videos)
    model = load_model(args.filepath)
    model.layers[-9].trainable = True
    model.layers[-10].trainable = True
    model.compile(optimizer=Adam(lr=K.get_value(model.optimizer.lr) * 0.5, decay=1e-6),
                  loss='categorical_crossentropy',
                  metrics=['acc'])
    print('Fine-tune top 2 convolutional layers of VGG19')
    model.fit_generator(generator=train_videos,
                        epochs=args.epochs,
                        callbacks=callbacks,
                        workers=args.num_workers,
                        validation_data=valid_videos)


if __name__ == '__main__':
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    train()
