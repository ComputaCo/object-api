import inspect
from typing import Any, Generic, TypeVar


def attr_is_list(class_type: object, attr_name: str) -> bool:
    # early exit
    if not hasattr(class_type, attr_name):
        return False
    value = getattr(class_type, attr_name)
    # plain check
    if isinstance(value, list):
        return True
    # look in annotations
    if hasattr(class_type, "__annotations__"):
        annotations = getattr(class_type, "__annotations__")
        if attr_name in annotations:
            return issubclass(annotations[attr_name], list)
    return False


def attr_is_dict(class_type: object, attr_name: str) -> bool:
    # early exit
    if not hasattr(class_type, attr_name):
        return False
    value = getattr(class_type, attr_name)
    # plain check
    if isinstance(value, dict):
        return True
    # look in annotations
    if hasattr(class_type, "__annotations__"):
        annotations = getattr(class_type, "__annotations__")
        if attr_name in annotations:
            return issubclass(annotations[attr_name], dict)
    return False


def get_class_attr_type(class_type: type, attr_name: str) -> type:
    if not hasattr(class_type, attr_name):
        return None
    return getattr(class_type, "__annotations__", {}).get(attr_name, None) or type(
        getattr(class_type, attr_name, None)
    )


def get_class_list_attr_generic_type(class_type: type, list_name: str) -> type:
    try:
        T = get_class_attr_type(class_type, list_name).__args__[0]
    except:
        if len(getattr(class_type, list_name)) > 0:
            T = type(getattr(class_type, list_name)[0])
        else:
            T = Any
    return T


def get_class_dict_attr_generic_types(
    class_type: type, dict_name: str
) -> tuple[type, type]:
    try:
        Tkey = get_class_attr_type(class_type, dict_name).__args__[0]
        Tvalue = get_class_attr_type(class_type, dict_name).__args__[1]
    except:
        if len(getattr(class_type, dict_name)) > 0:
            Tkey = type(list(getattr(class_type, dict_name).keys())[0])
            Tvalue = type(list(getattr(class_type, dict_name).values())[0])
        else:
            Tkey = str
            Tvalue = Any
    return Tkey, Tvalue


class MultiList(list):
    """
    # Test case 1: Initialize a MultiList with multiple sublists
    ml = MultiList([1, 2, 3], [4, 5, 6], [7, 8, 9])
    print(f"MultiList after initialization: {ml}")

    # Test case 2: Access elements via indexing
    print(f"Element at index 0: {ml[0]}")
    print(f"Element at index 3: {ml[3]}")
    print(f"Element at index 8: {ml[8]}")

    # Test case 3: Modify elements via indexing
    ml[0] = 10
    ml[3] = 40
    ml[8] = 90
    print(f"MultiList after modifying elements: {ml}")

    # Test case 4: Delete elements via indexing
    del ml[0]
    del ml[2]
    del ml[5]
    print(f"MultiList after deleting elements: {ml}")

    # Test case 5: Insert elements at a specific index
    ml.insert(0, 100)
    ml.insert(2, 200)
    ml.insert(5, 300)
    print(f"MultiList after inserting elements: {ml}")

    # Test case 6: Append elements
    ml.append(400)
    print(f"MultiList after appending an element: {ml}")

    # Test case 7: Remove a specific element
    ml.remove(200)
    print(f"MultiList after removing an element: {ml}")

    # Test case 8: Iterate over all elements
    print("Iterating over all elements:")
    for i in ml:
        print(i)

    # Test case 9: Print the MultiList
    print(f"MultiList: {ml}")

    # Test case 10: Print the repr of the MultiList
    print(f"Repr of MultiList: {repr(ml)}")
    """

    def __init__(self, *args):
        # store the sublists
        self._sublists = args

    def _locate(self, index):
        # keep a running total of sublist sizes
        running_total = 0
        for i, sublist in enumerate(self._sublists):
            running_total += len(sublist)
            if index < running_total:
                sublist_index = index - (running_total - len(sublist))
                return sublist, sublist_index
        raise IndexError("MultiList index out of range")

    def __getitem__(self, index):
        sublist, sublist_index = self._locate(index)
        return sublist[sublist_index]

    def __setitem__(self, index, value):
        sublist, sublist_index = self._locate(index)
        sublist[sublist_index] = value

    def __delitem__(self, index):
        sublist, sublist_index = self._locate(index)
        del sublist[sublist_index]

    def insert(self, index, value):
        sublist, sublist_index = self._locate(index)
        sublist.insert(sublist_index, value)

    def append(self, value):
        self._sublists[-1].append(value)

    def remove(self, value):
        for sublist in self._sublists:
            if value in sublist:
                sublist.remove(value)
                return
        raise ValueError(f"{value} not in MultiList")

    def __iter__(self):
        for sublist in self._sublists:
            for item in sublist:
                yield item

    def __len__(self):
        return sum(len(sublist) for sublist in self._sublists)

    def __str__(self):
        return str(list(self))

    def __repr__(self):
        return f"MultiList({', '.join(repr(sublist) for sublist in self._sublists)})"


class MultiSet(set):
    """
    # Test case 1: Initialize a MultiSet with multiple subsets
    ms = MultiSet({1, 2, 3}, {4, 5, 6}, {7, 8, 9})
    print(f"MultiSet after initialization: {ms}")

    # Test case 2: Add elements
    ms.add(10)
    ms.add(20)
    print(f"MultiSet after adding elements: {ms}")

    # Test case 3: Remove a specific element
    ms.remove(1)
    print(f"MultiSet after removing an element: {ms}")

    # Test case 4: Check if an element is in the MultiSet
    print(f"Check if 2 is in the MultiSet: {2 in ms}")
    print(f"Check if 100 is in the MultiSet: {100 in ms}")

    # Test case 5: Iterate over all elements
    print("Iterating over all elements:")
    for i in ms:
        print(i)

    # Test case 6: Print the MultiSet
    print(f"MultiSet: {ms}")

    # Test case 7: Print the repr of the MultiSet
    print(f"Repr of MultiSet: {repr(ms)}")
    """

    def __init__(self, *args):
        # store the subsets
        self._subsets = args

    def add(self, value):
        self._subsets[0].add(value)

    def remove(self, value):
        for subset in self._subsets:
            if value in subset:
                subset.remove(value)
                return
        raise KeyError(f"{value} not in MultiSet")

    def __contains__(self, value):
        return any(value in subset for subset in self._subsets)

    def __iter__(self):
        seen = set()
        for subset in self._subsets:
            for item in subset:
                if item not in seen:
                    seen.add(item)
                    yield item

    def __len__(self):
        return sum(1 for _ in self)

    def __str__(self):
        return str(set(self))

    def __repr__(self):
        return f"MultiSet({', '.join(repr(subset) for subset in self._subsets)})"


Targs = TypeVar("Targs")
Tretrn = TypeVar("Tretrn")
func = callable[[Targs], Tretrn]


class Decorator(Generic[Targs, Tretrn], callable[[func], func]):
    ...
