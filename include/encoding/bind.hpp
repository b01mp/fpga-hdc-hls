/**
 * @file bind.hpp   (Encoding)
 * @brief FUNCTION: bind  --  (a : HV, b : HV) -> HV  (element-wise associate).
 *
 *   Contract:      (a, b) -> out, out datatype inherited from inputs
 *   App (exposed):  element datatype, hv_dim (D)   (output-datatype override -> cast)
 *   Arch (deferred): dimension_parallelism, pipeline_mode, memory_space
 *
 * Binary baseline => XOR (self-inverse, distributes over bundling). Produces a
 * vector dissimilar to both inputs. Ported from emg_hdc; element type is now a
 * template argument.
 *
 * Datatype-parametric (Novelty 1): the bind op is selected at COMPILE time by a
 * family tag -- XOR (binary), multiply (bipolar/fixed/integer), sign-XOR plus
 * exponent-ADD (power-of-two, since 2^a * 2^b = 2^(a+b)). See bind_op below.
 *
 * STATUS: datatype-parametric (binary/bipolar/fixed/integer/pow2) + C-sim tested.
 */
#ifndef HDC_BIND_HPP
#define HDC_BIND_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// --- Per-family bind op, selected at COMPILE time by tag dispatch ---
//   binary : XOR       (self-inverse over {0,1})
//   bipolar: multiply  (self-inverse over {-1,+1})
//   fixed  : multiply
//   integer: multiply
//   pow2   : XOR the sign bits, ADD the exponents  (2^a * 2^b = 2^(a+b))
//            -- an adder, never a DSP. Exponent saturates inside pow2_pack.
//            NOTE: a raw `a + b` on the packed word is WRONG once a sign bit is
//            present, because the carry from the exponent field corrupts it.
template <typename T> inline T bind_op(T a, T b, binary_tag)  { return (T)(a ^ b); }
template <typename T> inline T bind_op(T a, T b, bipolar_tag) { return (T)(a * b); }
template <typename T> inline T bind_op(T a, T b, fixed_tag)   { return (T)(a * b); }
template <typename T> inline T bind_op(T a, T b, integer_tag) { return (T)(a * b); }
template <typename T> inline T bind_op(T a, T b, pow2_tag) {
    return (T)pow2_bind((pow2_t)a, (pow2_t)b);
}

// elem_t = element datatype, D = hv_dim, Family = datatype-family tag.
// Family defaults to binary_tag, so existing bind<elem_t,D>(...) calls are unchanged.
template <typename elem_t, int D, typename Family = binary_tag, int DP = 1>
void bind(const elem_t a[D], const elem_t b[D], elem_t out[D]){
    #pragma HLS ARRAY_PARTITION variable=a   type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=b   type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=out type=cyclic factor=DP dim=1
BIND_LOOP:
    for(int i = 0; i < D; i++){
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL factor=DP
        out[i] = bind_op(a[i], b[i], Family());
    }
}

} // namespace hdc

#endif // HDC_BIND_HPP
