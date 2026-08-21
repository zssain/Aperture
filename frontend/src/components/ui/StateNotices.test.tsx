import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { OfflineBanner } from "./OfflineBanner";
import { PartialDataNotice } from "./PartialDataNotice";
import { PermissionDenied } from "./PermissionDenied";
import { StaleDataBanner } from "./StaleDataBanner";

it("communicates every exceptional state with text, not colour alone", async () => {
  const { container } = render(<><OfflineBanner /><PartialDataNotice>One assessment is unavailable.</PartialDataNotice><PermissionDenied reason="Credit policy owner role required." /><StaleDataBanner message="Three new events arrived." onAction={() => undefined} /></>);
  expect(screen.getByText("Offline.")).toBeVisible();
  expect(screen.getByText("Partial data.")).toBeVisible();
  expect(screen.getByText("Permission denied")).toBeVisible();
  expect(screen.getByText("Newer data is available.")).toBeVisible();
  expect(await axe(container)).toHaveNoViolations();
});
