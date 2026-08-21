import { render } from "@testing-library/react";

import { Skeleton } from "./Skeleton";

describe("Skeleton", () => {
  it("renders an aria-hidden shimmer placeholder", () => {
    const { container } = render(<Skeleton className="h-4 w-24" />);
    const el = container.firstElementChild;
    expect(el).toHaveAttribute("aria-hidden", "true");
    expect(el?.className).toContain("shimmer");
  });
});
