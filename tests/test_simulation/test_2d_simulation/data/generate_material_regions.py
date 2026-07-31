#!/usr/bin/env python3
"""
Generate region polygon .dat files that reproduce the SYCL fish MaterialID
classifier (tests/tests_sycl/2d_examples/test_2d_flow_stream_around_fish_sycl/
2d_flow_stream_around_fish.h, FishMaterialInitialization::UpdateKernel::update,
and the ported PolynomialRegionMaterialId::UpdateKernel::update in
sphinxsim/sph_simulation/dynamics_builder/region_material_id.h) EXACTLY.

Ground truth conditions (quoted verbatim from
2d_flow_stream_around_fish.h:304-327):

    Real x = pos_[index_i][0] - cx_;
    Real y = pos_[index_i][1];

    Real y1 = a1_ * math::pow(x, Real(1)) + a2_ * math::pow(x, Real(2)) +
              a3_ * math::pow(x, Real(3)) + a4_ * math::pow(x, Real(4)) +
              a5_ * math::pow(x, Real(5));
    if (x <= (fish_length_ - head_length_) && y > (y1 - 0.004 + cy_) && y > (cy_ + bone_thickness_ / 2))
    {
        material_id_[index_i] = 0;
    }
    else if (x <= (fish_length_ - head_length_) && y < (-y1 + 0.004 + cy_) && y < (cy_ - bone_thickness_ / 2))
    {
        material_id_[index_i] = 0;
    }
    else if ((x > (fish_length_ - head_length_)) || ((y < (cy_ + bone_thickness_ / 2)) && (y > (cy_ - bone_thickness_ / 2))))
    {
        material_id_[index_i] = 2;
    }
    else
    {
        material_id_[index_i] = 1;
    }

with (2d_flow_stream_around_fish.h:190-194, :25-31):

    Real a1 = 1.22 * fish_thickness / fish_length;
    Real a2 = 3.19 * fish_thickness / fish_length / fish_length;
    Real a3 = -15.73 * fish_thickness / pow(fish_length, 3);
    Real a4 = 21.87 * fish_thickness / pow(fish_length, 4);
    Real a5 = -10.55 * fish_thickness / pow(fish_length, 5);

    cx = 0.3 * DL = 0.3 * 0.8 = 0.24
    cy = DH / 2 = 0.4 / 2 = 0.2
    fish_length = 0.2
    fish_thickness = 0.03
    head_length = 0.03
    bone_thickness = 0.003
    envelope_offset (the literal 0.004 above) = 0.004

fish.json (this branch) already targets this exact model via
sphinxsim/sph_simulation/dynamics_builder/region_material_id.h
(PolynomialRegionMaterialId), with region -> id mapping declared in
fish.json's material_id_regions:
    MuscleUpper -> 0, MuscleLower -> 0, Bone -> 2, default -> 1
(first listed region containing the point wins, else default).

Note the fifth-order polynomial y1(x) evaluated with a1..a5 (based on
fish_thickness) is *identical* to the top camber line of the fish skin
itself (tests_sycl/.../2d_fish_and_bones.h: outline(x, h=0.03, L=0.2) uses
the same a[0..4] formulas) -- i.e. y1(x) + cy is exactly the fish outline's
upper skin curve. So:
    skin_upper(x) = y1(x) + cy   skin_lower(x) = -y1(x) + cy
and the muscle bands are simply the strip between the skin and the skin
offset inward by 0.004, clipped to not cross the centreline core band.
"""
import re
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path

DATA_DIR = "/home/pruthvik/SPHinXsim/tests/test_simulation/test_2d_simulation/data"

# ----------------------------------------------------------------------
# Ground-truth constants, taken verbatim from the SYCL source.
# ----------------------------------------------------------------------
DL = 0.8
DH = 0.4
cx = 0.3 * DL                 # 0.24
cy = DH / 2                   # 0.2
fish_length = 0.2
fish_thickness = 0.03
head_length = 0.03
bone_thickness = 0.003
envelope_offset = 0.004
particle_spacing = 0.0025

a1 = 1.22 * fish_thickness / fish_length
a2 = 3.19 * fish_thickness / fish_length / fish_length
a3 = -15.73 * fish_thickness / fish_length**3
a4 = 21.87 * fish_thickness / fish_length**4
a5 = -10.55 * fish_thickness / fish_length**5

region_span = fish_length          # 0.2
tip_span = head_length             # 0.03
core_thickness = bone_thickness    # 0.003
half_core = core_thickness / 2     # 0.0015
body_cutoff = region_span - tip_span  # 0.17 (local x)


def y1_of(x_local):
    return (a1 * x_local + a2 * x_local**2 + a3 * x_local**3
            + a4 * x_local**4 + a5 * x_local**5)


def region_id(x_world, y_world):
    """Ground-truth classifier, reproducing the SYCL if/else EXACTLY
    (same order, same comparisons, same constants)."""
    x = x_world - cx
    y = y_world
    y1 = y1_of(x)
    if x <= body_cutoff and y > (y1 - envelope_offset + cy) and y > (cy + half_core):
        return 0
    elif x <= body_cutoff and y < (-y1 + envelope_offset + cy) and y < (cy - half_core):
        return 0
    elif (x > body_cutoff) or ((y < (cy + half_core)) and (y > (cy - half_core))):
        return 2
    else:
        return 1


# ----------------------------------------------------------------------
# STEP 2: real post-relaxation particle positions.
# ----------------------------------------------------------------------
VTP_PATH = "/home/pruthvik/sphinxsys/build_sycl/output_backup/FishBody_0000000000.vtp"
txt = open(VTP_PATH).read()
m = re.search(r'Name="Position".*?>\s*(.*?)\s*</DataArray>', txt, re.S)
vals = list(map(float, m.group(1).split()))
particles = np.array([(vals[i], vals[i + 1]) for i in range(0, len(vals), 3)])
print(f"Loaded {len(particles)} real post-relaxation FishBody particles from {VTP_PATH}")

# ----------------------------------------------------------------------
# STEP 3: build region polygons.
# ----------------------------------------------------------------------
outline_path_pts = np.loadtxt(f"{DATA_DIR}/fish_outline.dat")

N = 4000  # fine sampling, well under particle_spacing/4 = 0.000625 in x-step terms
xs_body = np.linspace(0.0, body_cutoff, N)          # local x, muscle/core region
xs_head = np.linspace(body_cutoff, fish_length, 400)  # local x, tail-cap ("head") region

skin_upper = lambda x: y1_of(x) + cy
skin_lower = lambda x: -y1_of(x) + cy


def build_muscle_upper():
    lower = np.maximum(skin_upper(xs_body) - envelope_offset, cy + half_core)
    upper = skin_upper(xs_body)
    mask = upper > lower + 1e-12
    xs = xs_body[mask]
    lo = lower[mask]
    up = upper[mask]
    top = np.column_stack([xs + cx, up])
    bot = np.column_stack([xs + cx, lo])[::-1]
    poly = np.vstack([top, bot, top[0:1]])
    return poly


def build_muscle_lower():
    upper = np.minimum(skin_lower(xs_body) + envelope_offset, cy - half_core)
    lower = skin_lower(xs_body)
    mask = upper > lower + 1e-12
    xs = xs_body[mask]
    lo = lower[mask]
    up = upper[mask]
    bot = np.column_stack([xs + cx, lo])
    top = np.column_stack([xs + cx, up])[::-1]
    poly = np.vstack([bot, top, bot[0:1]])
    return poly


def build_bone():
    """id-2 region: centreline core band (x <= body_cutoff) UNION tail cap
    (x > body_cutoff), both clipped to inside the actual fish skin.
    Built as one closed polygon tracing: up the core band's upper edge,
    across the tail cap (bounded by the true outline, not a rectangle),
    back along the core band's lower edge."""
    core_upper = np.minimum(skin_upper(xs_body), cy + half_core)
    core_lower = np.maximum(skin_lower(xs_body), cy - half_core)

    cap_upper = skin_upper(xs_head)
    cap_lower = skin_lower(xs_head)

    top = np.column_stack([np.concatenate([xs_body, xs_head]) + cx,
                            np.concatenate([core_upper, cap_upper])])
    bot = np.column_stack([np.concatenate([xs_body, xs_head]) + cx,
                            np.concatenate([core_lower, cap_lower])])[::-1]
    poly = np.vstack([top, bot, top[0:1]])
    return poly


muscle_upper_poly = build_muscle_upper()
muscle_lower_poly = build_muscle_lower()
bone_poly = build_bone()

np.savetxt(f"{DATA_DIR}/muscle_upper.dat", muscle_upper_poly, fmt="%.10f")
np.savetxt(f"{DATA_DIR}/muscle_lower.dat", muscle_lower_poly, fmt="%.10f")
np.savetxt(f"{DATA_DIR}/bone.dat", bone_poly, fmt="%.10f")
print("Wrote muscle_upper.dat, muscle_lower.dat, bone.dat")

# ----------------------------------------------------------------------
# STEP 4: self-validate.
# ----------------------------------------------------------------------
path_muscle_upper = Path(muscle_upper_poly)
path_muscle_lower = Path(muscle_lower_poly)
path_bone = Path(bone_poly)


def region_id_polygon(x_world, y_world):
    p = (x_world, y_world)
    if path_muscle_upper.contains_point(p, radius=1e-12):
        return 0
    if path_muscle_lower.contains_point(p, radius=1e-12):
        return 0
    if path_bone.contains_point(p, radius=1e-12):
        return 2
    return 1


truth = np.array([region_id(x, y) for x, y in particles])
poly_vec_upper = path_muscle_upper.contains_points(particles, radius=1e-12)
poly_vec_lower = path_muscle_lower.contains_points(particles, radius=1e-12)
poly_vec_bone = path_bone.contains_points(particles, radius=1e-12)

poly_ids = np.full(len(particles), 1, dtype=int)
poly_ids[poly_vec_bone] = 2
poly_ids[poly_vec_lower] = 0
poly_ids[poly_vec_upper] = 0

mismatch_mask = truth != poly_ids
n_mismatch = mismatch_mask.sum()

print("\n=== Validation ===")
print(f"{'region':>8} {'truth %':>10} {'polygon %':>10}")
for rid, name in [(0, "muscle"), (1, "tissue(default)"), (2, "bone")]:
    t_pct = 100.0 * (truth == rid).sum() / len(truth)
    p_pct = 100.0 * (poly_ids == rid).sum() / len(truth)
    print(f"{name:>16} {t_pct:9.3f}% {p_pct:9.3f}%")

print(f"\nMismatches: {n_mismatch} / {len(truth)} = {100.0*n_mismatch/len(truth):.4f}%")

if n_mismatch:
    print("\nMismatch coordinates (local x = world_x - cx, and distance to nearest boundary curve):")
    idx = np.where(mismatch_mask)[0]
    for i in idx:
        x_w, y_w = particles[i]
        xl = x_w - cx
        y1 = y1_of(xl)
        d_upper_skin = abs(y_w - (y1 + cy))
        d_lower_skin = abs(y_w - (-y1 + cy))
        d_upper_thr = abs(y_w - (y1 - envelope_offset + cy))
        d_lower_thr = abs(y_w - (-y1 + envelope_offset + cy))
        d_core_upper = abs(y_w - (cy + half_core))
        d_core_lower = abs(y_w - (cy - half_core))
        d_cutoff = abs(xl - body_cutoff)
        d_min = min(d_upper_thr, d_lower_thr, d_core_upper, d_core_lower, d_cutoff)
        print(f"  particle {i}: world=({x_w:.6f},{y_w:.6f}) truth={truth[i]} poly={poly_ids[i]} "
              f"min_dist_to_boundary={d_min:.6f}")

# ----------------------------------------------------------------------
# STEP 5: plots.
# ----------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(outline_path_pts[:, 0], outline_path_pts[:, 1], "k-", lw=1.2, label="fish_outline")
ax.plot(muscle_upper_poly[:, 0], muscle_upper_poly[:, 1], color="tab:red", lw=1.0, label="muscle_upper")
ax.plot(muscle_lower_poly[:, 0], muscle_lower_poly[:, 1], color="tab:orange", lw=1.0, label="muscle_lower")
ax.plot(bone_poly[:, 0], bone_poly[:, 1], color="tab:blue", lw=1.0, label="bone (id 2: core + tail-cap)")
ax.set_aspect("equal")
ax.set_title("Region polygons vs fish outline")
box = ax.get_position()
ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])
ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
fig.savefig(f"{DATA_DIR}/regions_check.png", dpi=150)
print(f"\nSaved {DATA_DIR}/regions_check.png")

fig2, ax2 = plt.subplots(figsize=(9, 5))
colors = {0: "tab:red", 1: "tab:green", 2: "tab:blue"}
labels = {0: "muscle (id 0)", 1: "tissue/default (id 1)", 2: "bone (id 2)"}
for rid in [0, 1, 2]:
    sel = truth == rid
    ax2.scatter(particles[sel, 0], particles[sel, 1], s=3, color=colors[rid], label=labels[rid])
ax2.set_aspect("equal")
ax2.set_title("Real particles coloured by ground-truth region_id(x,y)")
box2 = ax2.get_position()
ax2.set_position([box2.x0, box2.y0, box2.width * 0.75, box2.height])
ax2.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
fig2.savefig(f"{DATA_DIR}/regions_particles_truth.png", dpi=150)
print(f"Saved {DATA_DIR}/regions_particles_truth.png")
