# AUTOGENERATED! DO NOT EDIT! File to edit: 00_core.ipynb (unless otherwise specified).

__all__ = ['shape_list', 'maskTF', 'SelfAttentionTF', 'TransformerBlockTF', 'CTransformerTF']

# Cell
import tensorflow as tf

# Cell
# https://github.com/huggingface/transformers/blob/master/transformers/modeling_tf_utils.py
def shape_list(x):
    """Deal with dynamic shape in tensorflow cleanly."""
    static = x.shape.as_list()
    dynamic = tf.shape(x)
    return [dynamic[i] if s is None else s for i, s in enumerate(static)]

# Cell
def maskTF(matrices, mask_value=0.0, mask_diagonal=True):
  b, h, w = matrices.shape
  assert h == w

  mask = (1 - tf.linalg.band_part(tf.ones((h, h)), -1, 0)) * tf.float32.min
  masked = matrices - mask

  return masked

# Cell
class SelfAttentionTF(tf.keras.Model):
  def __init__(self, emb, heads, mask=False):
    super(SelfAttentionTF, self).__init__()

    self.emb = emb
    self.heads = heads
    self.mask = mask

    self.tokeys = tf.keras.layers.Dense(emb * heads, input_shape=(emb,), use_bias=False)
    self.toqueries = tf.keras.layers.Dense(emb * heads, input_shape=(emb,), use_bias=False)
    self.tovalues = tf.keras.layers.Dense(emb * heads, input_shape=(emb,), use_bias=False)
    self.unifyheads = tf.keras.layers.Dense(emb, input_shape=(emb * heads,))

  def call(self, x):
    b, t, e = shape_list(x)
    h = self.heads
    assert e == self.emb, f'Input embedding dim ({e}) should match layer embedding dim ({self.emb})'

    keys = tf.reshape(self.tokeys(x), [b, t, h, e])
    queries = tf.reshape(self.toqueries(x), [b, t, h, e])
    values = tf.reshape(self.tovalues(x), [b, t, h, e])
    # compute scaled dot-product self-attention

    # - fold heads into the batch dimension
    keys = tf.reshape( tf.transpose(keys, perm=[0, 2, 1, 3]), [b * h, t, e] )
    queries = tf.reshape( tf.transpose(queries, perm=[0, 2, 1, 3]), [b * h, t, e] )
    values = tf.reshape( tf.transpose(values, perm=[0, 2, 1, 3]), [b * h, t, e] )

    queries = queries / (e ** (1/4))
    keys    = keys / (e ** (1/4))
    # - Instead of dividing the dot products by sqrt(e), we scale the keys and values.
    #   This should be more memory efficient

    # - get dot product of queries and keys, and scale
    dot = tf.matmul(queries, tf.transpose(keys, perm=[0, 2, 1]))
    #assert 1 == 1
    #assert shape_list(dot) == [b * h, t, t]

    if self.mask: # mask out the upper half of the dot matrix, excluding the diagonal
      dot = maskTF(dot, mask_value=float('-inf'), mask_diagonal=False)

    dot = tf.nn.softmax(dot, axis=2)
    # - dot now has row-wise self-attention probabilities

    # apply the self attention to the values
    out = tf.reshape(tf.matmul(dot, values), [b, h, t, e])

    # swap h, t back, unify heads
    out = tf.reshape(tf.transpose(out, perm=[0, 2, 1, 3]), [b, t, h * e])

    return self.unifyheads(out)

# Cell
class TransformerBlockTF(tf.keras.Model):

  def __init__(self, emb, heads, mask, seq_length, ff_hidden_mult=4, dropout=0.0):
    super(TransformerBlockTF, self).__init__()

    self.attention = SelfAttentionTF(emb, heads=heads, mask=mask)
    self.mask = mask

    self.norm1 = tf.keras.layers.LayerNormalization()
    self.norm2 = tf.keras.layers.LayerNormalization()

    self.ff = tf.keras.Sequential([
      tf.keras.layers.Dense(ff_hidden_mult * emb, input_shape=(emb,), activation='relu'),
      tf.keras.layers.Dense(emb)
    ])

    self.do = tf.keras.layers.Dropout(dropout)

  def call(self, x):
    attended = self.attention(x)
    x = self.norm1(attended + x)
    x = self.do(x)
    fedforward = self.ff(x)
    x = self.norm2(fedforward + x)
    x = self.do(x)
    return x

# Cell
class CTransformerTF(tf.keras.Model):
    def __init__(self, emb, heads, depth, seq_length, num_tokens, num_classes, max_pool=True, dropout=0.0):
        super(CTransformerTF, self).__init__()

        self.num_tokens, self.max_pool = num_tokens, max_pool
        self.token_embedding = tf.keras.layers.Embedding(num_tokens, emb, input_length=seq_length)
        self.pos_embedding = tf.keras.layers.Embedding(seq_length, emb, input_length=seq_length)

        tblocks = []
        for i in range(depth):
            tblocks.append(TransformerBlockTF(emb=emb, heads=heads, seq_length=seq_length, mask=False, dropout=dropout))

        self.tblocks = tf.keras.Sequential(tblocks)
        self.toprobs = tf.keras.layers.Dense(num_classes, input_shape=(emb,))
        #self.do =

    def call(self, x):
        """
        :param x: A batch by sequence length integer tensor of token indices.
        :return: predicted log-probability vectors for each token based on the preceding tokens.
        """
        tokens = self.token_embedding(x)
        b, t, e = shape_list(tokens)

        positions = tf.tile(self.pos_embedding(tf.range(t))[None, :, :], [b, 1, 1])
        x = tokens + positions
        #dropout

        x = self.tblocks(x)
        #TODO max pooling vs. ave pooling
        x = tf.reduce_mean(x, axis=1)
        x = self.toprobs(x)
        return tf.nn.softmax(x, axis=1)