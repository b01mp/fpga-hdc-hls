"""
meshhd_sketch.py

Minimal, synthetic-data sketch of the MeshHD pipeline (Han et al., DATE 2026):

  1. Random Fourier Feature (RFF) mesh basis for an H x W pixel layout (Algorithm 1)
  2. Multi-scale bundling of several RFF bases (different sigma) into one basis
  3. Kronecker factorization of that basis into small factors K1, K2, K3
  4. Encoding an image two ways (dense vs. factorized) and checking they agree
  5. A toy 2-class classification via prototype bundling + cosine similarity

This is a scoping / correctness-of-understanding exercise on SMALL SYNTHETIC
tensors. It is not meant to reproduce the paper's reported accuracy, and there
is no dataset loading, no training loop chasing benchmark numbers, and no
evolution-strategy hyperparameter search.

Dimensions are kept small for fast, readable iteration:
    D  = 256   (hypervector / bundled basis dimension)
    H  = W = 8 (pixel mesh layout)          -> F = H*W = 64 pixels
    b1 = b2 = 8 (Kronecker factor ranks)
"""

import torch

torch.manual_seed(42)

# ----------------------------------------------------------------------------
# Global dimensions
# ----------------------------------------------------------------------------
D = 256
H = W = 8
F = H * W           # 64 pixels
b1 = b2 = 8          # Kronecker factor sizes (b1 * b2 == F)


# ==============================================================================
# STAGE 1 — RFF mesh basis (Algorithm 1)
# ==============================================================================
def rff_mesh_basis(H, W, D, sigma, generator):
    """
    Build an F x D random-Fourier-feature basis over an H x W pixel mesh.

    p_i       : normalized 2D coordinate of pixel i, in [0, 1) x [0, 1)
    w_j, b_j  : random frequency / phase for j = 1 .. D/2
    B[i,2j]   = cos(w_j . p_i + b_j)
    B[i,2j+1] = sin(w_j . p_i + b_j)
    B *= sqrt(2/D)
    """
    assert D % 2 == 0

    # Normalized coordinate grid p_i in [0,1), flattened row-major (h outer, w inner)
    # so pixel index i = h*W + w. This ordering is reused everywhere else (Stage 4)
    # so the dense and factorized encodings stay consistent.
    hs = torch.arange(H, dtype=torch.float32) / H
    ws = torch.arange(W, dtype=torch.float32) / W
    grid_h, grid_w = torch.meshgrid(hs, ws, indexing="ij")   # each [H, W]
    P = torch.stack([grid_h.flatten(), grid_w.flatten()], dim=1)  # [F, 2], row-major

    half = D // 2
    # w_j ~ N(0, I2) / sigma
    w = torch.randn(half, 2, generator=generator) / sigma     # [D/2, 2]
    # b_j ~ Unif[0, 2*pi)
    b = torch.rand(half, generator=generator) * 2 * torch.pi  # [D/2]

    phase = P @ w.T + b  # [F, D/2]  (broadcasts b over rows)

    B = torch.empty(F, D)
    B[:, 0::2] = torch.cos(phase)
    B[:, 1::2] = torch.sin(phase)
    B = B * (2.0 / D) ** 0.5

    assert B.shape == (F, D), f"expected {(F, D)}, got {tuple(B.shape)}"
    return B


def stage1_demo():
    print("=" * 70)
    print("STAGE 1 — RFF mesh basis")
    print("=" * 70)

    gen = torch.Generator().manual_seed(1)
    B = rff_mesh_basis(H, W, D, sigma=1.0, generator=gen)
    print(f"B.shape = {tuple(B.shape)}  (expected ({F}, {D}))")

    # neighboring pixels: (0,0) and (0,1)  ->  row-major indices 0 and 1
    # distant pixels:     (0,0) and (7,7)  ->  row-major indices 0 and 63
    i_near_a, i_near_b = 0, 1
    i_far_a, i_far_b = 0, F - 1

    dot_near = torch.dot(B[i_near_a], B[i_near_b]).item()
    dot_far = torch.dot(B[i_far_a], B[i_far_b]).item()

    print(f"dot(neighbor pixels (0,0)-(0,1)) = {dot_near:.4f}")
    print(f"dot(distant pixels   (0,0)-(7,7)) = {dot_far:.4f}")
    assert dot_near > dot_far, "expected neighboring pixels to be more similar than distant ones"
    print("OK: neighboring pixels are more similar than distant pixels.\n")

    return B


# ==============================================================================
# STAGE 2 — Multi-scale bundling
# ==============================================================================
def stage2_demo():
    print("=" * 70)
    print("STAGE 2 — Multi-scale bundling")
    print("=" * 70)

    sigmas = [0.5, 1.0, 2.0]
    alpha = [1 / 3, 1 / 3, 1 / 3]

    bases = []
    for k, sigma in enumerate(sigmas):
        gen = torch.Generator().manual_seed(100 + k)  # distinct frequencies per scale
        Bk = rff_mesh_basis(H, W, D, sigma=sigma, generator=gen)
        bases.append(Bk)
        print(f"  sigma={sigma:>4} -> basis shape {tuple(Bk.shape)}")

    B_bar = sum(a * Bk for a, Bk in zip(alpha, bases))

    print(f"B_bar.shape = {tuple(B_bar.shape)}  (expected ({F}, {D}))")
    assert B_bar.shape == (F, D)
    print("OK: multi-scale convex bundling preserves basis shape.\n")

    return B_bar


# ==============================================================================
# STAGE 3 — Kronecker factorization
# ==============================================================================
def stage3_factorize(B_bar, epochs=4000, lr=0.01):
    """
    Learn K1 (H x b2), K2 (W x b1), K3 ((b1*b2) x D) such that

        kron(K1, K2) @ K3  ~=  B_bar

    Note on Kronecker ordering: we factor with kron(K1, K2) (not kron(K2, K1))
    because that ordering matches the row-major pixel flattening (h*W + w) used
    in Stage 1 and Stage 4 -- i.e. it makes x_flat @ kron(K1, K2) equal to
    flatten(K1.T @ X @ K2) exactly. With this convention, kron(K1, K2) is a
    generic invertible F x F (64x64) matrix, so an exact K3 exists for any
    invertible K1, K2; Adam just needs to find well-conditioned factors.
    K1/K2 are orthogonally initialized (instead of small random) so kron(K1,K2)
    starts well-conditioned, and a cosine-annealed learning rate avoids the
    loss bouncing around a plateau instead of settling near zero.
    """
    print("=" * 70)
    print("STAGE 3 — Kronecker factorization")
    print("=" * 70)

    torch.manual_seed(7)
    K1 = torch.nn.init.orthogonal_(torch.empty(H, b2)).requires_grad_(True)
    K2 = torch.nn.init.orthogonal_(torch.empty(W, b1)).requires_grad_(True)
    K3 = (0.1 * torch.randn(b1 * b2, D)).requires_grad_(True)

    opt = torch.optim.Adam([K1, K2, K3], lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    for epoch in range(epochs):
        opt.zero_grad()
        recon = torch.kron(K1, K2) @ K3          # [F, F] @ [F, D] -> [F, D]
        loss = torch.norm(recon - B_bar, p="fro")
        loss.backward()
        opt.step()
        sched.step()
        if epoch % 100 == 0 or epoch == epochs - 1:
            print(f"  epoch {epoch:4d}  loss = {loss.item():.6f}")

    print(f"K1.shape = {tuple(K1.shape)}  (expected ({H}, {b2}))")
    print(f"K2.shape = {tuple(K2.shape)}  (expected ({W}, {b1}))")
    print(f"K3.shape = {tuple(K3.shape)}  (expected ({b1 * b2}, {D}))")
    assert K1.shape == (H, b2)
    assert K2.shape == (W, b1)
    assert K3.shape == (b1 * b2, D)
    print("OK: factor shapes match the paper's Kronecker decomposition.\n")

    return K1.detach(), K2.detach(), K3.detach()


# ==============================================================================
# STAGE 4 — Encoding via two paths (dense vs. factorized)
# ==============================================================================
def stage4_demo(B_bar, K1, K2, K3):
    print("=" * 70)
    print("STAGE 4 — Encoding: dense vs. factorized (key check)")
    print("=" * 70)

    gen = torch.Generator().manual_seed(99)
    X = torch.randn(H, W, generator=gen)   # synthetic image
    x_flat = X.flatten()                   # [F], row-major (h*W + w), matches B_bar rows

    # --- Dense path -----------------------------------------------------
    HV_dense = x_flat @ B_bar              # [F] @ [F, D] -> [D]

    # --- Factorized path --------------------------------------------------
    t1 = X @ K2                  # [H, W] @ [W, b1] -> [H, b1]
    t2 = K1.T @ t1                # [b2, H] @ [H, b1] -> [b2, b1]
    HV_kron = t2.flatten() @ K3   # [b1*b2] @ [b1*b2, D] -> [D]

    norm_dense = torch.norm(HV_dense).item()
    norm_kron = torch.norm(HV_kron).item()
    rel_err = (torch.norm(HV_dense - HV_kron) / torch.norm(HV_dense)).item()

    print(f"HV_dense.shape = {tuple(HV_dense.shape)}  (expected ({D},))")
    print(f"HV_kron.shape  = {tuple(HV_kron.shape)}  (expected ({D},))")
    print(f"||HV_dense|| = {norm_dense:.4f}")
    print(f"||HV_kron||  = {norm_kron:.4f}")
    print(f"relative error = {rel_err * 100:.4f} %")

    assert HV_dense.shape == (D,)
    assert HV_kron.shape == (D,)
    assert rel_err < 0.01, f"relative error {rel_err:.4%} exceeds 1% tolerance"
    print("OK: dense and factorized encodings agree within 1%.\n")

    return HV_dense


# ==============================================================================
# STAGE 5 — Minimal classification
# ==============================================================================
def stage5_demo():
    print("=" * 70)
    print("STAGE 5 — Minimal classification")
    print("=" * 70)

    gen = torch.Generator().manual_seed(123)
    n_per_class = 20

    # Synthetic class-conditional hypervectors: class 0 centered at +1, class 1 at -1
    class0_samples = 1.0 + 0.3 * torch.randn(n_per_class, D, generator=gen)
    class1_samples = -1.0 + 0.3 * torch.randn(n_per_class, D, generator=gen)

    # Bundle: sum + normalize -> class prototypes
    proto0 = class0_samples.sum(dim=0)
    proto0 = proto0 / torch.norm(proto0)
    proto1 = class1_samples.sum(dim=0)
    proto1 = proto1 / torch.norm(proto1)

    print(f"proto0.shape = {tuple(proto0.shape)}  (expected ({D},))")
    print(f"proto1.shape = {tuple(proto1.shape)}  (expected ({D},))")

    # Noisy query drawn from class 0's distribution
    query = 1.0 + 0.3 * torch.randn(D, generator=gen)

    prototypes = torch.stack([proto0, proto1])              # [2, D]
    sims = torch.nn.functional.cosine_similarity(
        query.unsqueeze(0), prototypes, dim=1
    )                                                        # [2]
    pred = torch.argmax(sims).item()

    print(f"cosine similarities = {sims.tolist()}")
    print(f"predicted class = {pred} (expected 0)")
    assert pred == 0, "expected the class-0 query to be classified as class 0"
    print("OK: noisy class-0 query correctly classified.\n")


# ==============================================================================
# Main
# ==============================================================================
if __name__ == "__main__":
    stage1_demo()
    B_bar = stage2_demo()
    K1, K2, K3 = stage3_factorize(B_bar)
    stage4_demo(B_bar, K1, K2, K3)
    stage5_demo()

    print("=" * 70)
    print("All stages completed and all assertions passed.")
    print("=" * 70)
