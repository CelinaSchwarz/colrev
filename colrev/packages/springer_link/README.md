## Summary
Springer Nature is a leading global scientific, technical, and medical publisher, with metadata for over 16 million online documents, encompassing journal articles, book chapters, and protocols published by Springer.

This package allows you to perform DB searches and API searches using the SpringerLink API. By configuring and using this class, you can retrieve and manage metadata from Springer Nature's vast database of scholarly articles and books.

## search

The search for this Springer package is launched with the following command in your ColRev project:

```
colrev search --add colrev.springer_link
```

Upon entering the above command the user is asked to choose between  `DB search` and `API search` (For more details on the searchtypes see manual of CoLRev). The user can select the search type by navigating through the list with `uparrow` and `downarrow` and confirm the choice with `enter`.

### DB search

For this search download search results and store in `data/search/` directory.

### API search

Springer Link only allows a daily quota of 500. This might lead to the site being unavailable with a response code of 403.

#### API search: API key for Springer Link

After selecting API search the user is asked to enter an API key for Springer Link (available upon [registration](https://dev.springernature.com/)). If an API key is already stored, the user can change the key with the first prompted question by navigating through the list with `downarrow` and selecting `yes`. Pressing `enter` will confirm this selection.
The use of an API key is mandatory.

The user can choose between `yes` for searching with a complex query or `no` for search parameters by navigating through the list with `downarrow` and confirming the choice by pressing `enter`.

#### API search: complex query

The user can type the individual search constraints that can also use the boolean  `AND`, `OR` , `NOT`, `NEAR` for a specified search. Following conditions have to be followed:
- Search terms must be enclosed in double quotes `"`
- The entire logical condition must be enclosed in parentheses `()`
- Filters can be added with a `space` and then followed by the `constraint:argument`
- A word or phrase that appears among the constraints but is not preceded by a constraint value will be treated as the argument of the "empty constraint"

##### Examples

- A single search term: `("saturn") type:book`
- Two terms with AND: `("saturn" AND "jupiter") type:book`
- Two terms with OR: `("saturn" OR "jupiter") type:book`
- Negation of a term: `("saturn" NOT "jupiter") type:book`
- After NEAR, a slash `/{number}` should be used, for example: `("saturn" NEAR/10 "jupiter") type:book`

##### Other Constraints supported by the Springers Nature API

- `doi:` 10.1007/s11214-017-0458-1
- `pub:` Extremes
- `onlinedate:` 2019-03-29
    - also wildcard, e.g., `onlinedate:` 2019-01-*
    - `onlinedatefrom:` 2019-09-01%20 `onlinedateto:` 2019-12-31
- `country:` %22New%20Zealand%22
- `isbn:` 978-0-387-79148-7
- `issn:` 1861-0692
- `journalid:` 392
- `date:` 2010-03-01
- `issuetype:` Supplement
- `issn:` 1861-0692
- `journalid:` 259

For additional contraints visit the SpringerLink API Documentation (Link below).

#### API search: entering the search paramters

In this step the user can enter the search parameters into the console.
The user can provide values for the following parameters: keyword, subject, language, year and type. Pressing `enter` will confirm the choice. If the field is blank, this parameter will be skipped. The parameters should be entered as followed:

- `keyword:` e.g. onlinear.
- `subject:`  Springer Nature supports the following subject areas:
    - Astronomy
    - Behavioral Sciences
    - Biomedical Sciences
    - Business and Management
    - Chemistry
    - Climate
    - Computer Science
    - Earth Sciences
    - Economics
    - Education and Language
    - Energy
    - Engineering
    - Environmental Sciences
    - Food Science and Nutrition
    - General Interest
    - Geography
    - Law
    - Life Sciences
    - Materials
    - Mathematics
    - Medicine
    - Philosophy
    - Physics
    - Public Health
    - Social Sciences
    - Statistics
    - Water
- `language:` please use country codes, e.g. "de" for "Germany".
- `year:` e.g. 2024.
- `type:` limit search to Book or Journal.

Each constraint that appears in your request will be automatically ANDed with all the others.

#### API search: Search results

After retrieving the data from Springer, they are transformed into the standard CoLRev `BibTex` format and saved in the distinctive resultfile `data/search/springer_link{number}.bib`.
Please note, that unfortunately, the format of Springer_Link's output does not produce sufficiently clear information to fill in every CoLRev field. Disparities, e.g. in the definition of content types(=="ENTRYTYPES" in CoLRev), may lead to ambigous information about a paper, its type or its venue. To prevent misinformation, papers will be marked as `miscellaneous`, if the publication type is not determinable. Furthermore, the Field regarding books, such as address are not supported by Springers Nature.
In addition to that, the given url may not work due an error 404.

## Links

- [SpringerLink](https://link.springer.com/)
- [SpringerLink API](https://dev.springernature.com/)
- [SpringerLink API Documentation](https://docs-dev.springernature.com/docs/)
