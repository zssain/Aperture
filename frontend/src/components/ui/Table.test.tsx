import { render, screen } from "@testing-library/react";

import { Table } from "./Table";
import type { Column } from "./Table";

interface Row {
  id: string;
  name: string;
  amount: number;
}

const columns: Column<Row>[] = [
  { key: "name", header: "Name", render: (row) => row.name },
  {
    key: "amount",
    header: "Amount",
    isNumeric: true,
    sortable: true,
    render: (row) => row.amount,
  },
];

describe("Table", () => {
  it("renders rows, right-aligns numerics and exposes aria-sort", () => {
    render(
      <Table<Row>
        caption="Cases"
        columns={columns}
        rows={[{ id: "1", name: "Alpha", amount: 5 }]}
        getRowId={(row) => row.id}
        sort={{ key: "amount", direction: "asc" }}
        onSort={() => undefined}
      />,
    );
    expect(screen.getByRole("columnheader", { name: "Amount" })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    expect(screen.getByText("5").closest("td")?.className).toContain("text-right");
  });

  it("renders skeleton rows while loading, preserving the column count", () => {
    const { container } = render(
      <Table<Row>
        caption="Cases"
        columns={columns}
        rows={[]}
        getRowId={(row) => row.id}
        loading
        skeletonRows={3}
      />,
    );
    expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
    expect(container.querySelectorAll("tbody tr:first-child td")).toHaveLength(2);
  });
});
