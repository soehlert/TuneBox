import React from "react";
import { Button } from "@mui/material";

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  paginate: (pageNumber: number) => void;
  className?: string;  // Added className prop
}

const Pagination: React.FC<PaginationProps> = ({ currentPage, totalPages, paginate, className }) => {
  const pageNumbers = [];

  // Generate the list of page numbers with logic to include only the pages you want
  for (let i = 1; i <= totalPages; i++) {
    if (
      i === 1 ||
      i === totalPages ||
      (i >= currentPage - 1 && i <= currentPage + 1)
    ) {
      pageNumbers.push(i);
    }
  }

  return (
    <div className={`${className} pagination`}>
      <Button
        variant="contained"
        color="primary"
        onClick={() => paginate(1)}
        disabled={currentPage === 1}
      >
        &laquo; First
      </Button>
      <Button
        variant="contained"
        color="primary"
        onClick={() => paginate(currentPage - 1)}
        disabled={currentPage === 1}
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
      >
        Next &gt;
      </Button>
      <Button
        variant="contained"
        color="primary"
        onClick={() => paginate(totalPages)}
        disabled={currentPage === totalPages}
      >
        Last &raquo;
      </Button>
    </div>
  );
};

export default Pagination;
