import os
import pickle
import random
import math
import tensorflow as tf

from modeler.network import Network
import modeler.sampling as sampling

def train(savedir, params):
    """Train a model with the given input data file."""

    if os.path.isdir(savedir):
        # savedir exists, so load existing parameters
        with open(os.path.join(savedir, 'params.pkl'), 'rb') as fh:
            params = pickle.load(fh)
    else:
        # otherwise write the new parameters
        os.makedirs(savedir, exist_ok=True)
        with open(os.path.join(savedir, 'params.pkl'), 'wb') as fh:
            pickle.dump(params, fh)

    with open(params.datafile, 'rb') as handler:
        # load the samples generated by the preprocessor
        samples, authors = pickle.load(handler)
        vocab_size = max(max(samples))
        author_size = max(authors) + 1

    # initialize the network graph
    network = Network(vocab_size, author_size, **vars(params))
    global_step = tf.Variable(0, name='global_step', trainable=False)
    learning_rate = tf.train.exponential_decay(
        params.learn_rate,
        global_step,
        params.decay_steps,
        params.decay_rate,
        staircase=True
    )
    train_step = tf.train \
        .AdamOptimizer(learning_rate) \
        .minimize(network.loss_node, global_step=global_step)
    tf.summary.scalar('loss', network.loss_node)


    config = tf.ConfigProto(allow_soft_placement=True)
    # begin a new tensorflow session
    sess = tf.Session(config=config)
    sess.run(tf.global_variables_initializer())

    with tf.name_scope('saver'):
        # create a saver to store training progress
        saver = tf.train.Saver()
        writer = tf.summary.FileWriter(savedir, sess.graph)
        # track summary ops
        summaries = tf.summary.merge_all()

        # load the saved model if it already exists
        ckpt = tf.train.get_checkpoint_state(savedir)
        if ckpt and ckpt.model_checkpoint_path:
            saver.restore(sess, ckpt.model_checkpoint_path)

    # file to store model checkpoints in
    checkfile = os.path.join(savedir, 'model.ckpt')

    # calculate where to start training based on saved progress
    step = sess.run(global_step)
    epoch = step // math.ceil(len(samples) / params.batch_size) + 1
    offset = (step % math.ceil(len(samples) / params.batch_size)) * params.batch_size

    for epoch in range(epoch, params.num_epochs+1):
        sample_gen = sampling.batch_samples(
            samples[offset:], authors[offset:], params.batch_size
        )
        for batch in sample_gen:
            sequence, target, auths = batch

            err, summary, step, _ = sess.run(
                [network.loss_node, summaries, global_step, train_step],
                feed_dict={
                    network.seq_node: sequence,
                    network.auth_node:  auths,
                    network.target_node: target,
                }
            )

            print('Epoch: ', epoch, 'Step: ', step, 'Loss: ', err)
            writer.add_summary(summary, step)
            if step % 100 == 0:
                saver.save(sess, os.path.join(checkfile), global_step)

        # reset saved offset for next epoch
        offset = 0

    saver.save(sess, os.path.join(checkfile), step)
    print('Checkpoint saved.')
