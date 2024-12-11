import React from "react";
import { Button } from "@mui/material";

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  paginate: (pageNumber: number) => void;
  className?: string;  // Added className prop
}

const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  paginate,
  className,
}) => {
  const pageNumbers = [];

  // Logic for pagination: 4 pages before and after the current page
  const leftSide = Math.max(currentPage - 3, 1);
  const rightSide = Math.min(currentPage + 3, totalPages);

  // Add page numbers from the calculated range
  for (let i = leftSide; i <= rightSide; i++) {
    pageNumbers.push(i);
  }

  return (
    <div className={`${className} pagination`}>
      <Button
        variant="contained"
        color="primary"
        onClick={() => paginate(1)}
        disabled={currentPage === 1}
        className="pagination-first-prev"

      >
        &laquo; First
      </Button>
      <Button
        variant="contained"
        color="primary"
        onClick={() => paginate(currentPage - 1)}
        disabled={currentPage === 1}
        className="pagination-first-prev"
      >
        &lt; Prev
      </Button>

      {pageNumbers.map((page) => (
        <Button
          key={page}
          variant="contained"
          color={page === currentPage ? "secondary" : "primary"}
          onClick={() => paginate(page)}
        >
          {page}
        </Button>
      ))}

      <Button
        variant="contained"
        color="primary"
        onClick={() => paginate(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="pagination-next-last"

      >
        Next &gt;
      </Button>
      <Button
        variant="contained"
        color="primary"
        onClick={() => paginate(totalPages)}
        disabled={currentPage === totalPages}
        className="pagination-next-last"
      >
        Last &raquo;
      </Button>
    </div>
  );
};


export default Pagination;
