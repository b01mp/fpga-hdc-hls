/**
 * @file flatten.hpp   (Encoding)
 * @brief FUNCTION: flatten  --  (in : HM) -> HV  (reshape to vector).
 *
 *   Contract:      (in[R][C]) -> out[R*C]   (row-major)
 *   App (exposed):  - (datatype inherited)
 *   Arch (deferred): pipeline_mode
 *
 * STATUS: implemented; C-sim pending.
 */
#ifndef HDC_FLATTEN_HPP
#define HDC_FLATTEN_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype. out[R*C] = row-major flatten of in[R][C].
template <typename elem_t, int R, int C>
void flatten(const elem_t in[R][C], elem_t out[R * C]) {
FLATTEN_ROW:
    for (int r = 0; r < R; r++)
    FLATTEN_COL:
        for (int c = 0; c < C; c++)
            out[r * C + c] = in[r][c];
}

} // namespace hdc

#endif // HDC_FLATTEN_HPP
