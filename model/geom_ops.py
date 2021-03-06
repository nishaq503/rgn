"""
Geometric TensorFlow operations for protein structure prediction.

There are some common conventions used throughout.

BATCH_SIZE is the size of the batch, and may vary from iteration to iteration.
NUM_STEPS is the length of the longest sequence in the data set (not batch).
        It is fixed as part of the tf graph.
NUM_DIHEDRALS is the number of dihedral angles per residue (phi, psi, omega).
        It is always 3.
NUM_DIMENSIONS is a constant of nature, the number of physical spatial dimensions.
        It is always 3.

In general, this is an implicit ordering of tensor dimensions that is respected throughout.
It is:
    NUM_STEPS, BATCH_SIZE, NUM_DIHEDRALS, NUM_DIMENSIONS

The only exception is when NUM_DIHEDRALS are fused into NUM_STEPS.
Btw what is setting the standard is the builtin interface of tensorflow.models.rnn.rnn,
 which expects NUM_STEPS x [BATCH_SIZE, NUM_AAS].
"""

__author__ = "Mohammed AlQuraishi"
__copyright__ = "Copyright 2018, Harvard Medical School"
__license__ = "MIT"

import collections

import numpy as np
import tensorflow as tf

# Constants
NUM_DIMENSIONS = 3
NUM_DIHEDRALS = 3
BOND_LENGTHS = np.array([145.801, 152.326, 132.868], dtype='float32')
BOND_ANGLES = np.array([2.124, 1.941, 2.028], dtype='float32')


# Functions
def angularize(input_tensor,
               name=None):
    """
    Restricts real-valued tensors to the interval (-pi, pi] by feeding them through a cosine.
    """

    with tf.name_scope(name, 'angularize', [input_tensor]) as scope:
        input_tensor = tf.convert_to_tensor(input_tensor, name='input_tensor')

        return tf.multiply(np.pi, tf.cos(input_tensor + (np.pi / 2)), name=scope)


def reduce_mean_angle(radii,
                      angles,
                      use_complex=False,
                      name=None):
    """
    Computes the weighted mean of angles.
    Accepts option to compute use complex exponentials or real numbers.

    Complex number-based version is giving wrong gradients for some reason,
    but forward calculation is fine.

    See https://en.wikipedia.org/wiki/Mean_of_circular_quantities

    Args:
        radii: [BATCH_SIZE, NUM_ANGLES]
        angles:  [NUM_ANGLES, NUM_DIHEDRALS]

    Returns:
        [BATCH_SIZE, NUM_DIHEDRALS]
    """

    with tf.name_scope(name, 'reduce_mean_angle', [radii, angles]) as scope:
        radii = tf.convert_to_tensor(radii, name='radii')
        angles = tf.convert_to_tensor(angles, name='angles')

        if use_complex:
            # use complex-valued exponentials for calculation
            c_rads = tf.complex(radii, 0.)  # cast to complex numbers
            exps = tf.exp(tf.complex(0., angles))  # convert to point on complex plane

            # take the weighted mixture of the unit circle coordinates
            unit_coords = tf.matmul(c_rads, exps)

            # return angle of averaged coordinate
            return tf.angle(unit_coords, name=scope)

        else:
            # use real-numbered pairs of values
            sines = tf.sin(angles)
            cosines = tf.cos(angles)

            y_coords = tf.matmul(radii, sines)
            x_coords = tf.matmul(radii, cosines)

            return tf.atan2(y_coords, x_coords, name=scope)


def reduce_l2_norm(input_tensor,
                   reduction_indices=None,
                   keep_dims=None,
                   weights=None,
                   epsilon=1e-12,
                   name=None):
    """
    Computes the (possibly weighted) L2 norm of a tensor along
     the dimensions given in reduction_indices.

    Args:
        input_tensor: [..., NUM_DIMENSIONS, ...]
        weights: [..., NUM_DIMENSIONS, ...]

    Returns: [..., ...]
    """

    with tf.name_scope(name, 'reduce_l2_norm', [input_tensor]) as scope:
        input_tensor = tf.convert_to_tensor(input_tensor, name='input_tensor')

        input_tensor_sq = tf.square(input_tensor)
        if weights is not None:
            input_tensor_sq = input_tensor_sq * weights

        return tf.sqrt(tf.maximum(tf.reduce_sum(input_tensor_sq,
                                                axis=reduction_indices,
                                                keep_dims=keep_dims),
                                  epsilon),
                       name=scope)


def reduce_l1_norm(input_tensor,
                   reduction_indices=None,
                   keep_dims=None,
                   weights=None,
                   non_negative=True,
                   name=None):
    """
    Computes the (possibly weighted) L1 norm of a tensor
     along the dimensions given in reduction_indices.

    Args:
        input_tensor: [..., NUM_DIMENSIONS, ...]
        weights: [..., NUM_DIMENSIONS, ...]

    Returns: [..., ...]
    """

    with tf.name_scope(name, 'reduce_l1_norm', [input_tensor]) as scope:
        input_tensor = tf.convert_to_tensor(input_tensor, name='input_tensor')

        if not non_negative:
            input_tensor = tf.abs(input_tensor)
        if weights is not None:
            input_tensor = input_tensor * weights

        return tf.reduce_sum(input_tensor,
                             axis=reduction_indices,
                             keep_dims=keep_dims,
                             name=scope)


def dihedral_to_point(dihedral,
                      r=BOND_LENGTHS,
                      theta=BOND_ANGLES,
                      name=None):
    """
    Takes triplets of dihedral angles (phi, psi, omega)
     and returns 3D points ready for use in reconstruction of coordinates.
    Bond lengths and angles are based on idealized averages.

    Args:
        dihedral: [NUM_STEPS, BATCH_SIZE, NUM_DIHEDRALS]

    Returns:
        [NUM_STEPS x NUM_DIHEDRALS, BATCH_SIZE, NUM_DIMENSIONS]
    """

    with tf.name_scope(name, 'dihedral_to_point', [dihedral]) as scope:
        # [NUM_STEPS, BATCH_SIZE, NUM_DIHEDRALS]
        dihedral = tf.convert_to_tensor(dihedral, name='dihedral')

        num_steps = tf.shape(dihedral)[0]

        # important to use get_shape() to keep batch_size fixed for performance reasons
        batch_size = dihedral.get_shape().as_list()[1]

        # [NUM_DIHEDRALS]
        r_cos_theta = tf.constant(r * np.cos(np.pi - theta), name='r_cos_theta')
        # [NUM_DIHEDRALS]
        r_sin_theta = tf.constant(r * np.sin(np.pi - theta), name='r_sin_theta')

        # [NUM_STEPS, BATCH_SIZE, NUM_DIHEDRALS]
        pt_x = tf.tile(tf.reshape(r_cos_theta, [1, 1, -1]),
                       [num_steps, batch_size, 1],
                       name='pt_x')
        # [NUM_STEPS, BATCH_SIZE, NUM_DIHEDRALS]
        pt_y = tf.multiply(tf.cos(dihedral),
                           r_sin_theta,
                           name='pt_y')
        # [NUM_STEPS, BATCH_SIZE, NUM_DIHEDRALS]
        pt_z = tf.multiply(tf.sin(dihedral),
                           r_sin_theta,
                           name='pt_z')

        # [NUM_DIMS, NUM_STEPS, BATCH_SIZE, NUM_DIHEDRALS]
        pt = tf.stack([pt_x, pt_y, pt_z])
        # [NUM_STEPS, NUM_DIHEDRALS, BATCH_SIZE, NUM_DIMS]
        pt_perm = tf.transpose(pt, perm=[1, 3, 2, 0])
        # [NUM_STEPS x NUM_DIHEDRALS, BATCH_SIZE, NUM_DIMS]
        pt_final = tf.reshape(pt_perm,
                              [num_steps * NUM_DIHEDRALS, batch_size, NUM_DIMENSIONS],
                              name=scope)

        return pt_final


def point_to_coordinate(pt,
                        num_fragments=6,
                        parallel_iterations=4,
                        swap_memory=False,
                        name=None):
    """
    Takes points from dihedral_to_point and sequentially converts
     them into the coordinates of a 3D structure.

    Reconstruction is done in parallel, by independently reconstructing num_fragments
     fragments and then reconstituting the chain at the end in reverse order.
    The core reconstruction algorithm is NeRF,
     based on DOI: 10.1002/jcc.20237 by Parsons et al. 2005.
    The parallelized version is described in XXX.

    Args:
        pt: [NUM_STEPS x NUM_DIHEDRALS, BATCH_SIZE, NUM_DIMENSIONS]

    Opts:
        num_fragments: Number of fragments to reconstruct in parallel.
                       If None, the number is chosen adaptively

    Returns:
        [NUM_STEPS x NUM_DIHEDRALS, BATCH_SIZE, NUM_DIMENSIONS]
    """

    with tf.name_scope(name, 'point_to_coordinate', [pt]) as scope:
        pt = tf.convert_to_tensor(pt, name='pt')

        # compute optimal number of fragments if needed
        s = tf.shape(pt)[0]  # NUM_STEPS x NUM_DIHEDRALS
        if num_fragments is None:
            num_fragments = tf.cast(tf.sqrt(tf.cast(s, dtype=tf.float32)), dtype=tf.int32)

        # initial three coordinates (specifically chosen to eliminate need for extraneous matmul)
        Triplet = collections.namedtuple('Triplet', 'a, b, c')
        batch_size = pt.get_shape().as_list()[1]  # BATCH_SIZE
        init_mat = np.array([[-np.sqrt(1.0 / 2.0), np.sqrt(3.0 / 2.0), 0],
                             [-np.sqrt(2.0), 0, 0], [0, 0, 0]],
                            dtype='float32')

        # NUM_DIHEDRALS x [NUM_FRAGS, BATCH_SIZE, NUM_DIMENSIONS]
        init_coords = Triplet(
            *[tf.reshape(tf.tile(row[np.newaxis],
                                 tf.stack([num_fragments * batch_size, 1])),
                         [num_fragments, batch_size, NUM_DIMENSIONS]) for row in init_mat])

        # pad points to yield equal-sized fragments
        # (NUM_FRAGS x FRAG_SIZE) - (NUM_STEPS x NUM_DIHEDRALS)
        r = ((num_fragments - (s % num_fragments)) % num_fragments)

        # [NUM_FRAGS x FRAG_SIZE, BATCH_SIZE, NUM_DIMENSIONS]
        pt = tf.pad(pt, [[0, r], [0, 0], [0, 0]])

        # [NUM_FRAGS, FRAG_SIZE,  BATCH_SIZE, NUM_DIMENSIONS]
        pt = tf.reshape(pt,
                        [num_fragments, -1, batch_size, NUM_DIMENSIONS])
        # [FRAG_SIZE, NUM_FRAGS,  BATCH_SIZE, NUM_DIMENSIONS]
        pt = tf.transpose(pt, perm=[1, 0, 2, 3])

        # extension function used for single atom reconstruction and whole fragment alignment
        def extend(tri, point, multi_m):
            """
            Args:
                tri: NUM_DIHEDRALS x [NUM_FRAGS/0, BATCH_SIZE, NUM_DIMENSIONS]
                point: [NUM_FRAGS/FRAG_SIZE, BATCH_SIZE, NUM_DIMENSIONS]
                multi_m: bool indicating whether m (and tri) is higher rank.
                         pt is always higher rank;
                         what changes is what the first rank is.
            """

            # [NUM_FRAGS/0, BATCH_SIZE, NUM_DIMS]
            bc = tf.nn.l2_normalize(tri.c - tri.b, -1, name='bc')

            # [NUM_FRAGS/0, BATCH_SIZE, NUM_DIMS]
            n = tf.nn.l2_normalize(tf.cross(tri.b - tri.a, bc), -1, name='n')

            # multiple fragments, one atom at a time.
            if multi_m:
                # [NUM_FRAGS,   BATCH_SIZE, NUM_DIMS, 3 TRANS]
                m = tf.transpose(tf.stack([bc, tf.cross(n, bc), n]),
                                 perm=[1, 2, 3, 0],
                                 name='m')
            else:  # single fragment, reconstructed entirely at once.
                # FRAG_SIZE, BATCH_SIZE, NUM_DIMS, 3 TRANS
                s_ = tf.pad(tf.shape(point), [[0, 1]],
                            constant_values=3)
                # [BATCH_SIZE, NUM_DIMS, 3 TRANS]
                m = tf.transpose(tf.stack([bc, tf.cross(n, bc), n]),
                                 perm=[1, 2, 0])
                # [FRAG_SIZE, BATCH_SIZE, NUM_DIMS, 3 TRANS]
                m = tf.reshape(tf.tile(m, [s_[0], 1, 1]),
                               s_, name='m')

            # [NUM_FRAGS/FRAG_SIZE, BATCH_SIZE, NUM_DIMS]
            coord = tf.add(tf.squeeze(tf.matmul(m, tf.expand_dims(point, 3)),
                                      axis=3),
                           tri.c,
                           name='coord')
            return coord

        # loop over FRAG_SIZE in NUM_FRAGS parallel fragments,
        # sequentially generating the coordinates for each fragment across all batches
        i = tf.constant(0)
        s_padded = tf.shape(pt)[0]  # FRAG_SIZE
        coords_ta = tf.TensorArray(tf.float32,
                                   size=s_padded,
                                   tensor_array_name='coordinates_array')

        # FRAG_SIZE x [NUM_FRAGS, BATCH_SIZE, NUM_DIMENSIONS]
        def loop_extend(i_, tri, coords_ta_):
            coord = extend(tri, pt[i_], True)
            return [i_ + 1, Triplet(tri.b, tri.c, coord), coords_ta_.write(i_, coord)]

        # NUM_DIHEDRALS x [NUM_FRAGS, BATCH_SIZE, NUM_DIMENSIONS],
        # FRAG_SIZE x [NUM_FRAGS, BATCH_SIZE, NUM_DIMENSIONS]
        _, tris, coords_pre_trans_ta = tf.while_loop(lambda i_, _1, _2: i_ < s_padded,
                                                     loop_extend,
                                                     [i, init_coords, coords_ta],
                                                     parallel_iterations=parallel_iterations,
                                                     swap_memory=swap_memory)

        # loop over NUM_FRAGS in reverse order,
        # bringing all the downstream fragments in alignment with current fragment

        # [NUM_FRAGS, FRAG_SIZE, BATCH_SIZE, NUM_DIMENSIONS]
        coords_pre_trans = tf.transpose(coords_pre_trans_ta.stack(),
                                        perm=[1, 0, 2, 3])

        # NUM_FRAGS
        i = tf.shape(coords_pre_trans)[0]

        def loop_trans(i_, coords_):
            transformed_coords = extend(Triplet(*[di[i_] for di in tris]), coords_, False)
            return [i_ - 1, tf.concat([coords_pre_trans[i_], transformed_coords], 0)]

        # [NUM_FRAGS x FRAG_SIZE, BATCH_SIZE, NUM_DIMENSIONS]
        _, coords_trans = tf.while_loop(lambda i_, _: i_ > -1,
                                        loop_trans,
                                        [i - 2, coords_pre_trans[-1]],
                                        parallel_iterations=parallel_iterations,
                                        swap_memory=swap_memory)

        # lose last atom and pad from the front to gain an atom ([0,0,0],
        # consistent with init_mat), to maintain correct atom ordering
        # [NUM_STEPS x NUM_DIHEDRALS, BATCH_SIZE, NUM_DIMENSIONS]
        coords = tf.pad(coords_trans[:s - 1], [[1, 0], [0, 0], [0, 0]],
                        name=scope)

        return coords


def drmsd(u, v, weights, name=None):
    """ Computes the dRMSD of two tensors of vectors.

        Vectors are assumed to be in the third dimension. Op is done element-wise over batch.

    Args:
        u, v: [NUM_STEPS, BATCH_SIZE, NUM_DIMENSIONS]
        weights: [NUM_STEPS, NUM_STEPS, BATCH_SIZE]

    Returns:
        [BATCH_SIZE]
    """

    with tf.name_scope(name, 'dRMSD', [u, v, weights]) as scope:
        u = tf.convert_to_tensor(u, name='u')
        v = tf.convert_to_tensor(v, name='v')
        weights = tf.convert_to_tensor(weights, name='weights')

        # [NUM_STEPS, NUM_STEPS, BATCH_SIZE]
        diffs = pairwise_distance(u) - pairwise_distance(v)
        # [BATCH_SIZE]
        norms = reduce_l2_norm(diffs,
                               reduction_indices=[0, 1],
                               weights=weights,
                               name=scope)

        return norms


def pairwise_distance(u, name=None):
    """
    Computes the pairwise distance (l2 norm) between all vectors in the tensor.
    Vectors are assumed to be in the third dimension.
    Op is done element-wise over batch.

    Args:
        u: [NUM_STEPS, BATCH_SIZE, NUM_DIMENSIONS]

    Returns:
        [NUM_STEPS, NUM_STEPS, BATCH_SIZE]
    """
    with tf.name_scope(name, 'pairwise_distance', [u]) as scope:
        u = tf.convert_to_tensor(u, name='u')

        # [NUM_STEPS, NUM_STEPS, BATCH_SIZE, NUM_DIMENSIONS]
        diffs = u - tf.expand_dims(u, 1)

        # [NUM_STEPS, NUM_STEPS, BATCH_SIZE]
        norms = reduce_l2_norm(diffs, reduction_indices=[3], name=scope)

        return norms
