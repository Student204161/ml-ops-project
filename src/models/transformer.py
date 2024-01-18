import torch
from torch import nn
from einops.layers.torch import Rearrange
from einops import repeat

class PatchEmbedding(nn.Module):
    """Patch Embeddings for Vision Transformer
    Args:
        in_channels: int, number of input channels
        d_model: int, model dimensionality
        img_shape: tuple, shape of the image
        patch_shape: tuple, shape of the patch
    """
    def __init__(self,in_channels, d_model, img_shape, patch_shape):
        super(PatchEmbedding, self).__init__()
        self.d_model = d_model
        self.patch_height, self.patch_width = eval(patch_shape)
        self.image_height, self.image_width = eval(img_shape)

        self.patch_dim = in_channels * self.patch_height * self.patch_width
        self.num_patches = (self.image_height // self.patch_height) * (self.image_width // self.patch_width)


        self.to_patch_embedding = nn.Sequential(
            Rearrange('b c (h p1) (w p2) -> b (h w) (p1 p2 c)', p1 = self.patch_height, p2 = self.patch_width),
            nn.LayerNorm(self.patch_dim),
            nn.Linear(self.patch_dim, d_model),
            nn.LayerNorm(d_model),
        )

        self.pos_embedding = nn.Parameter(torch.randn(1, self.num_patches + 1, d_model))
        self.cls_token = nn.Parameter(torch.randn(1, 1, d_model))


    def forward(self, x):
        x = self.to_patch_embedding(x) # [B, C, H, W] --> [B, num_patches, d_model]
        b, n, _ = x.shape
        cls_tokens = repeat(self.cls_token, '1 1 d -> b 1 d', b = b)
        x = torch.cat((cls_tokens, x), dim=1)
        x += self.pos_embedding[:, :(n + 1)].to('cuda', dtype=x.dtype) if torch.cuda.is_available() else self.pos_embedding[:, :(n + 1)]
        return x

class MultiHeadAttentionBlock(nn.Module):
    """Multihead attention block for TransformerBlock
    Args:
        d_model: int, model dimensionality 
        n_heads: int, number of heads
        attn_dropout: float, dropout rate

    """
    def __init__(
            self,
            d_model: int,
            num_heads: int,
            attn_dropout: float,
            ):
        super(MultiHeadAttentionBlock, self).__init__()

        self.normlayer = nn.LayerNorm(d_model)
        self.attention = nn.MultiheadAttention(d_model, num_heads, attn_dropout)

    def forward(self,x):
        x = self.normlayer(x)
        x, _ = self.attention(x, x, x)
        return x


class FeedForward(nn.Module):
    """Feed forward module for TransformerBlock
    Args:
        d_model: int, model dimensionality
        mlp_size: int, size of the hidden layer
        mlp_dropout: float, dropout rate
    """
    
    def __init__(self, d_model, mlp_size, mlp_dropout):
        super().__init__()
        self.layernorm = nn.LayerNorm(normalized_shape = d_model)
        self.mlp = nn.Sequential(
            nn.Linear(in_features = d_model, out_features = mlp_size),
            nn.GELU(),
            nn.Dropout(p = mlp_dropout),
            nn.Linear(in_features = mlp_size, out_features = d_model),
            nn.Dropout(p = mlp_dropout)
        )

    def forward(self, x):
        return self.mlp(self.layernorm(x))

class TransformerBlock(nn.Module):
    """Transformer block for Vision Transformer
    Args:
        d_model: int, model dimensionality
        mlp_dropout: float, dropout rate
        attn_dropout: float, dropout rate
        mlp_size: int, size of the hidden layer
        num_heads: int, number of heads
    
    """

    def __init__(self, d_model,
               mlp_dropout,
               attn_dropout,
               mlp_size,
               num_heads,
               ):
        super().__init__()

        self.msa_block = MultiHeadAttentionBlock(d_model = d_model,
                                                    num_heads = num_heads,
                                                    attn_dropout = attn_dropout)

        self.ff_block = FeedForward(d_model = d_model,
                                                        mlp_size = mlp_size,
                                                        mlp_dropout = mlp_dropout,
                                                        )

    def forward(self,x):
        x = self.msa_block(x) + x
        x = self.ff_block(x) + x

        return x


class ViT(nn.Module):
    """
    Vision Transformer (ViT)
    Architecture based on the paper https://arxiv.org/pdf/2010.11929.pdf


    Args:
        img_shape: tuple, shape of the image
        in_channels: int, number of input channels
        patch_shape: tuple, shape of the patch
        d_model: int, model dimensionality
        num_transformer_layers: int, number of transformer layers
        dropout_rate: float, dropout rate
        mlp_size: int, size of the hidden layer
        num_heads: int, number of heads
        num_classes: int, number of classes
        batch_size: int, batch size
    """

    def __init__(self, img_shape = (160, 106),
               in_channels = 4,
               patch_shape = (32, 53), #should be factor of 160 and 106
               d_model = 512,
               num_transformer_layers = 2, # from table 1 above
               dropout_rate = 0.2,
               mlp_size = 1048,
               num_heads = 4,
               num_classes = 1): #regression problem, so only one output:
        super().__init__()

        self.patch_embedding_layer = PatchEmbedding(in_channels = in_channels,
                                                        patch_shape = patch_shape,
                                                        d_model = d_model,
                                                        img_shape = img_shape) 

        self.transformer_encoder = nn.Sequential(*[TransformerBlock(d_model = d_model,
                                                mlp_dropout = dropout_rate,
                                                attn_dropout = dropout_rate,
                                                mlp_size = mlp_size,
                                                num_heads = num_heads) for _ in range(num_transformer_layers)])

        self.classifier = nn.Sequential(nn.LayerNorm(normalized_shape = d_model),
                                        nn.Linear(in_features = d_model,
                                                out_features = num_classes))

    def forward(self, x):
        x = self.classifier(self.transformer_encoder(self.patch_embedding_layer(x)))
        return x.mean(dim = 1)
