from dataclasses import dataclass

from price_slice import PriceSlice


@dataclass
class PriceSliceBundle:
    slices: list[PriceSlice]

    def __len__(self):
        return len(self.slices)

    def __getitem__(self, index: int):
        return self.slices[index]
